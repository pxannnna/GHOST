"""Score aircraft-geometry templates directly against a time-frequency spectrum.

No free ridge tracker is used to select a path: frequency at every time is fixed
by one supplied Doppler multiplier curve and one emitted source tone. Tone is
selected on training columns only; held-out columns and negative controls gate
acceptance. Thresholds are engineering heuristics, not confidence probabilities.
"""
import numpy as np


def _validate(freq, db):
    freq = np.asarray(freq, dtype=float)
    db = np.asarray(db, dtype=float)
    if freq.ndim != 1 or len(freq) < 5 or db.ndim != 2 or db.shape[0] != len(freq):
        raise ValueError('Expected frequency vector and frequency x time spectrogram')
    if not np.isfinite(freq).all() or np.any(np.diff(freq) <= 0):
        raise ValueError('Frequency bins must be finite and increasing')
    spacing = float(np.median(np.diff(freq)))
    if not np.allclose(np.diff(freq), spacing, rtol=1e-3, atol=1e-8):
        raise ValueError('Expected uniformly spaced frequency bins')
    return freq, db, spacing


def local_contrast(freq, db):
    """dB above neighbouring frequency shoulders, retaining stationary tones.

    Broad speech/noise bursts raise both the tested frequency and its shoulders.
    Keeping stationary tones here allows an explicit constant-tone null check.
    """
    freq, db, spacing = _validate(freq, db)
    shifts = np.unique(np.maximum(1, np.rint(np.array([3, 5, 8]) / spacing).astype(int)))
    shoulders = []
    indices = np.arange(len(freq))
    for shift in shifts:
        for sign in [-1, 1]:
            shoulders.append(db[np.clip(indices + sign * shift, 0, len(freq)-1)])
    background = np.median(np.stack(shoulders), axis=0)
    contrast = np.clip(db - background, -18, 60)
    contrast[~np.isfinite(db)] = np.nan
    return contrast


def _sample(freq, spectrum, predictions, tolerance_hz=.75):
    """Sample a small, fixed-width tube; no independently movable ridge nodes."""
    spacing = freq[1] - freq[0]
    safe = np.where(np.isfinite(predictions), predictions, freq[0]-100)
    indices = np.rint((safe-freq[0])/spacing).astype(np.int64)
    times = np.arange(spectrum.shape[1])
    sampled = np.full(predictions.shape, -np.inf)
    width = int(np.floor(tolerance_hz/spacing))
    # Include nearest bin, then at most a physically small +/- tolerance.
    for offset in range(-width, width+1):
        shifted = indices+offset
        inside = (shifted >= 0) & (shifted < len(freq))
        values = spectrum[np.clip(shifted, 0, len(freq)-1), times]
        values = np.where(inside & np.isfinite(values), values, -np.inf)
        sampled = np.maximum(sampled, values)
    valid = np.isfinite(predictions) & (predictions >= freq[0]) & (predictions <= freq[-1])
    return np.where(valid, sampled, -np.inf)


def _peak_bins(freq, contrast, columns, per_column=4):
    rows = []
    for column in columns:
        power = contrast[:, column]
        peaks = np.flatnonzero((power[1:-1] > power[:-2]) & (power[1:-1] >= power[2:]))+1
        peaks = peaks[np.isfinite(power[peaks])]
        order = peaks[np.argsort(power[peaks])[::-1]]
        chosen = []
        for index in order:
            if all(abs(freq[index]-freq[old]) >= 3 for old in chosen):
                chosen.append(int(index))
                if len(chosen) >= per_column:
                    break
        # Fixed shape: weak/no-peak anchors produce invalid f0 proposals.
        chosen += [-1] * (per_column-len(chosen))
        rows.append(chosen)
    return np.array(rows, dtype=int)


def _tone_proposals(freq, contrast, multipliers, training, max_tones):
    columns = np.flatnonzero(training)
    anchor_count = min(8, len(columns), max_tones)
    anchors = columns[np.unique(np.linspace(0,len(columns)-1,anchor_count).astype(int))]
    per_anchor = max(1, max_tones//len(anchors))
    peaks = _peak_bins(freq, contrast, anchors, per_anchor)
    observed = np.where(peaks >= 0, freq[np.maximum(peaks,0)], np.nan)
    with np.errstate(invalid='ignore', divide='ignore'):
        proposals = observed[None,:,:] / multipliers[:,anchors,None]
    return proposals.reshape(len(multipliers), -1)[:, :max_tones]


def scan_templates(freq, db, multipliers, source_frequencies=None, *, max_tones=32,
                   train_mask=None, minimum_score_db=6, minimum_margin_db=3,
                   minimum_support=.55, minimum_span_hz=6, batch_size=64,
                   require_span_for_selection=False, evidence=None, frequency_region=None):
    """Score N aircraft/receiver templates against an F x T dB spectrogram.

    ``multipliers`` is N x T, as returned by geometry.received_curve. Invalid
    geometry should be represented as NaN. A single missing spectrum column or
    invalid point rejects a full template, rather than rewarding selective fit.

    Optional ``evidence`` supplies precomputed spectral/event contrast in dB.
    It must be built without using validation columns to fit any background.

    With ``frequency_region``, a curve may enter/leave the observed band. Only
    its geometry-defined in-band portion is scored (minimum four train + four
    check samples and 30% of the event). Controls use those exact same times.
    The rest of the event is not interpreted as an absent aircraft tone.

    The optional f0 proposals may be a common K-vector or N x K matrix. Without
    these, strong spectral peaks on training anchors are dewarped by each model.
    Default training/validation columns alternate in blocks of four. Adjacent
    overlapping STFT windows remain correlated; this is an out-of-fit check,
    not independent statistical validation or a multiple-testing correction.

    Returns per-location arrays. Larger ``score`` is better: minimum training /
    validation contrast minus the stronger constant/shuffled-time control.
    Invalid templates have score=-inf and accepted=False. Source frequency and
    evidence fields are NaN when no valid proposal exists; sanitize before JSON.
    """
    freq, db, spacing = _validate(freq, db)
    multipliers = np.atleast_2d(np.asarray(multipliers, dtype=float))
    n, times = multipliers.shape
    if times != db.shape[1] or times < 12:
        raise ValueError('Need at least 12 aligned time columns')
    if max_tones < 1 or batch_size < 1:
        raise ValueError('max_tones and batch_size must be positive')
    train = ((np.arange(times)//4) % 2 == 0) if train_mask is None else np.asarray(train_mask,dtype=bool)
    if train.shape != (times,) or min(np.sum(train), np.sum(~train)) < 4:
        raise ValueError('Need at least four training and four validation columns')
    contrast = local_contrast(freq, db) if evidence is None else np.asarray(evidence, dtype=float)
    if contrast.shape != db.shape or (evidence is not None and not np.isfinite(contrast).all()):
        raise ValueError('Evidence must be finite and match spectrogram dimensions')
    if frequency_region is not None:
        low, high = map(float, frequency_region)
        if not freq[0] <= low < high <= freq[-1]:
            raise ValueError('Frequency region must lie within spectrum')
    def mean_active(values, active):
        # Explicit geometric frequency-window masking, not selection by measured
        # brightness. Missing audio and invalid flight geometry still reject.
        total=np.sum(np.where(active,values,0),axis=-1)
        count=np.sum(active,axis=-1)
        return np.where(count>0,total/np.maximum(count,1),-np.inf)
    proposal_contrast=contrast.copy()
    if frequency_region is not None:
        proposal_contrast[(freq<low)|(freq>high)]=-np.inf
    proposals = None if source_frequencies is None else np.asarray(source_frequencies,dtype=float)
    if proposals is not None:
        if proposals.ndim == 1:
            proposals = np.broadcast_to(proposals[None,:], (n,len(proposals)))
        if proposals.ndim != 2 or proposals.shape[0] != n or proposals.shape[1] == 0:
            raise ValueError('source_frequencies must be K or N x K')
    keys = ['score','source_frequency_hz','train_score','validation_score','constant_score',
            'shuffled_score','support_fraction','frequency_span_hz']
    result = {key: np.full(n,np.nan) for key in keys}
    result['score'][:] = -np.inf
    result['accepted'] = np.zeros(n,dtype=bool)
    result['valid'] = np.zeros(n,dtype=bool)
    result['support_mask'] = np.zeros((n,times),dtype=bool)
    result['training_mask'] = train.copy()
    result['validation_mask'] = (~train).copy()
    # Explicitly reject an incompletely observed window; caller can split gaps.
    if not np.isfinite(db).all():
        return result
    # A stationary alternative is chosen using training only, restricted later
    # to the frequency span of the proposed curve. This avoids unrelated mains
    # hum elsewhere in the band vetoing every aircraft tone.
    mean_train = np.mean(contrast[:,train],axis=1)
    top_constant = np.argsort(mean_train)[-min(32,len(freq)):]
    validation_indices = np.flatnonzero(~train)
    null_orders={count:[np.random.default_rng(917+count+257*k).permutation(count) for k in range(3)] for count in range(times+1)}
    for start in range(0,n,batch_size):
        stop = min(start+batch_size,n)
        factors = multipliers[start:stop]
        f0 = _tone_proposals(freq,proposal_contrast,factors,train,max_tones) if proposals is None else proposals[start:stop]
        predicted = factors[:,None,:] * f0[:,:,None]
        values = _sample(freq,contrast,predicted)
        active=np.ones(predicted.shape,dtype=bool) if frequency_region is None else ((predicted>=low)&(predicted<=high))
        validity = ((np.isfinite(values)|~active).all(axis=-1) & np.isfinite(f0)
                    & np.isfinite(factors).all(axis=-1)[:,None] & (factors>0).all(axis=-1)[:,None]
                    & (active[:,:,train].sum(axis=-1)>=4) & (active[:,:,~train].sum(axis=-1)>=4)
                    & (active.sum(axis=-1)>=max(8,int(np.ceil(.3*times)))))
        spans=np.max(np.where(active,predicted,-np.inf),axis=-1)-np.min(np.where(active,predicted,np.inf),axis=-1)
        if require_span_for_selection:
            # A near-horizontal fit is not a candidate Doppler event. Apply this
            # before tone selection, rather than letting hum win then rejecting it.
            validity &= spans >= minimum_span_hz
        training_scores = mean_active(values[:,:,train],active[:,:,train])
        training_scores = np.where(validity,training_scores,-np.inf)
        chosen = np.argmax(training_scores,axis=1)
        row = np.arange(stop-start)
        f = f0[row,chosen]
        prediction = predicted[row,chosen]
        observed = values[row,chosen]
        selected_active=active[row,chosen]
        valid = validity[row,chosen]
        train_score = training_scores[row,chosen]
        val_score = mean_active(observed[:,~train],selected_active[:,~train])
        support = mean_active(observed[:,~train] >= minimum_score_db,selected_active[:,~train])
        span = spans[row,chosen]
        constant_freq = np.broadcast_to(freq[top_constant],(len(factors),len(top_constant))).copy()
        lower = np.min(np.where(selected_active,prediction,np.inf),axis=-1)-2
        upper = np.max(np.where(selected_active,prediction,-np.inf),axis=-1)+2
        constant_freq[(constant_freq<lower[:,None])|(constant_freq>upper[:,None])] = np.nan
        # Always test a horizontal line through this model's mid-frequency.
        constant_freq = np.column_stack([constant_freq,np.median(prediction,axis=-1)])
        constant_predictions = np.broadcast_to(constant_freq[:,:,None], (*constant_freq.shape,times))
        constants = _sample(freq,contrast,constant_predictions)
        choice = np.argmax(mean_active(constants[:,:,train],selected_active[:,None,train]),axis=1)
        constant_score = mean_active(constants[row,choice][:,~train],selected_active[:,~train])
        shuffle_scores = []
        for repetition in range(3):
            # Preserve the SAME audio times and burst envelope. Permute only the
            # model frequencies among its evaluated check times. Shuffling audio
            # from quiet, out-of-band times would unfairly favour brief models
            # passing through any loud broadband burst.
            shuffled_prediction=prediction.copy()
            for i in range(len(prediction)):
                indices=validation_indices[selected_active[i,validation_indices]]
                shuffled_prediction[i,indices]=prediction[i,indices[null_orders[len(indices)][repetition]]]
            shuffled_values = _sample(freq,contrast,shuffled_prediction)
            shuffle_scores.append(mean_active(shuffled_values[:,~train],selected_active[:,~train]))
        shuffled_score = np.max(shuffle_scores,axis=0)
        null_score = np.maximum(constant_score,shuffled_score)
        with np.errstate(invalid='ignore'):
            score = np.minimum(train_score,val_score)-null_score
        accepted = valid & (train_score>=minimum_score_db) & (val_score>=minimum_score_db) & (support>=minimum_support) & (span>=minimum_span_hz) & (score>=minimum_margin_db)
        values_out = dict(score=np.where(valid,score,-np.inf),source_frequency_hz=f,
            train_score=train_score,validation_score=val_score,constant_score=constant_score,
            shuffled_score=shuffled_score,support_fraction=support,frequency_span_hz=span)
        for key,value in values_out.items():
            result[key][start:stop]=np.where(valid,value,-np.inf if key=='score' else np.nan)
        result['valid'][start:stop]=valid
        result['support_mask'][start:stop]=(observed>=minimum_score_db)&valid[:,None]&selected_active
        result['accepted'][start:stop]=accepted
    return result


def extract_support(freq, db, predicted_hz, *, sample_indices=None, min_contrast_db=6,
                    tolerance_hz=1):
    """Return observed spectral maxima close to a fixed model, never fabricated points.

    This is descriptive evidence AFTER direct spectral scoring. Feeding these
    model-conditioned points into a second ridge loss is not independent evidence.
    """
    freq, db, spacing = _validate(freq, db)
    predicted = np.asarray(predicted_hz,dtype=float)
    if predicted.shape != (db.shape[1],):
        raise ValueError('Expected one predicted frequency per time column')
    if sample_indices is not None and len(sample_indices)!=len(predicted):
        raise ValueError('sample_indices must match time columns')
    contrast = local_contrast(freq,db)
    points = []
    for column,target in enumerate(predicted):
        if not np.isfinite(target):continue
        indices = np.flatnonzero((np.abs(freq-target)<=tolerance_hz)&np.isfinite(contrast[:,column]))
        if not len(indices):continue
        index = indices[np.argmax(db[indices,column])]
        # Require a measured local maximum, not just the edge of a search tube.
        if index==0 or index==len(freq)-1:continue
        if not (db[index,column]>=db[index-1,column] and db[index,column]>=db[index+1,column]):continue
        prominence = float(contrast[index,column])
        if prominence<min_contrast_db:continue
        point = dict(column_index=column,frequency_hz=float(freq[index]),predicted_hz=float(target),
                     contrast_db=prominence,sigma_hz=max(float(spacing),.5))
        if sample_indices is not None:point['sample']=int(sample_indices[column])
        points.append(point)
    return points
