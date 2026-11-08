"""Match a fixed Doppler shape to sustained spectral ridges.

Every sample is taken on the predicted curve, after fixed frequency smoothing.
No local maximum, free ridge node or per-time frequency adjustment is allowed.
Scores are descriptive contrast in dB, not location probabilities. Alternating
time blocks are a consistency check, not statistically independent evidence.
"""
import numpy as np
from .intensity_match import sample_curve
from .model_score import _peak_bins


def smooth_frequency(values, spacing, sigma_hz=.5):
    radius=max(1,int(np.ceil(3*sigma_hz/spacing)))
    offsets=np.arange(-radius,radius+1)
    weights=np.exp(-.5*(offsets*spacing/sigma_hz)**2);weights/=weights.sum()
    padded=np.pad(values,((radius,radius),(0,0)),mode='edge')
    return sum(w*padded[radius+i:radius+i+len(values)] for i,w in zip(offsets,weights))


def block_statistics(values, active, blocks, parity):
    """Equal weight per time block, so a loud brief crossing cannot dominate."""
    means=[]
    for block in np.unique(blocks):
        if block%2!=parity:continue
        columns=blocks==block
        use=active[...,columns]
        count=use.sum(axis=-1)
        means.append(np.where(count>=2,(np.where(use,values[...,columns],0).sum(axis=-1)/np.maximum(count,1)),np.nan))
    if not means:
        shape=values.shape[:-1]
        return np.full(shape,-np.inf),np.zeros(shape),np.zeros(shape)
    means=np.stack(means,axis=-1)
    count=np.isfinite(means).sum(axis=-1)
    # A finite sentinel avoids all-NaN median warnings. Sort only valid values.
    ordered=np.sort(np.where(np.isfinite(means),means,np.inf),axis=-1)
    lo=np.maximum(0,(count-1)//2);hi=np.maximum(0,count//2)
    median=(np.take_along_axis(ordered,lo[...,None],axis=-1)[...,0]+
            np.take_along_axis(ordered,hi[...,None],axis=-1)[...,0])/2
    support=((means>=1)&np.isfinite(means)).sum(axis=-1)/np.maximum(count,1)
    return np.where(count>=2,median,-np.inf),support,count


def fit_sustained(frequency, evidence, factors, times, region, *, source_frequencies=None,
                  minimum_span=30, minimum_bend=3, minimum_duration=24):
    f=np.asarray(frequency);d=np.atleast_2d(factors);times=np.asarray(times)
    if evidence.shape!=(len(f),len(times)) or d.shape[1]!=len(times):
        raise ValueError('Aligned spectrum, Doppler factors and times required')
    if not np.isfinite(evidence).all() or np.any(np.diff(times)<=0):
        raise ValueError('Finite evidence and increasing times required')
    # Fixed .5 Hz Gaussian averages all nearby bins; never chooses a new peak.
    spectrum=smooth_frequency(np.clip(evidence,-12,18),f[1]-f[0])
    blocks=np.floor((times-times[0])/8).astype(int);training=blocks%2==0
    def evaluate(tones):
        pred=d[:,None,:]*tones[:,:,None]
        values,active=sample_curve(f,spectrum,pred,region)
        train,_,count=block_statistics(values,active,blocks,0)
        span=np.max(np.where(active,pred,-np.inf),axis=-1)-np.min(np.where(active,pred,np.inf),axis=-1)
        first=np.argmax(active,axis=-1);last=active.shape[-1]-1-np.argmax(active[...,::-1],axis=-1)
        begin=np.take_along_axis(pred,first[...,None],axis=-1)[...,0]
        end=np.take_along_axis(pred,last[...,None],axis=-1)[...,0]
        duration=times[last]-times[first]
        u=(times-times[first][...,None])/np.maximum(duration[...,None],1e-6)
        chord=begin[...,None]+(end-begin)[...,None]*u
        bend=np.max(np.where(active,abs(pred-chord),0),axis=-1)
        good=(np.isfinite(d).all(axis=-1)&(d>0).all(axis=-1))[:,None]
        good=good&np.isfinite(tones)&(tones>0)&(active.mean(axis=-1)>=.3)&(duration>=minimum_duration)&(span>=minimum_span)&(bend>=minimum_bend)&(count>=2)
        return np.where(good,train,-np.inf),pred,values,active,span
    if source_frequencies is None:
        available=np.flatnonzero(training)
        anchors=available[np.unique(np.linspace(0,len(available)-1,min(16,len(available))).astype(int))]
        peaks=_peak_bins(f,spectrum,anchors,4)
        obs=np.where(peaks>=0,f[np.maximum(peaks,0)],np.nan)
        tones=(obs[None,:,:]/d[:,anchors,None]).reshape(len(d),-1)
    else:
        tones=np.asarray(source_frequencies,dtype=float)
        if tones.ndim==1:tones=np.broadcast_to(tones,(len(d),len(tones)))
    score,*_=evaluate(tones)
    if source_frequencies is None:
        top=np.argsort(score,axis=-1)[:,-3:]
        centres=np.take_along_axis(tones,top,axis=-1)
        tones=(centres[:,:,None]+np.arange(-1,1.001,.125)).reshape(len(d),-1)
        score,*_=evaluate(tones)
    chosen=np.argmax(score,axis=-1);row=np.arange(len(d))
    tone=tones[row,chosen]
    train,pred,values,active,span=evaluate(tone[:,None])
    train=train[:,0];pred=pred[:,0];values=values[:,0];active=active[:,0];span=span[:,0]
    check,support,_=block_statistics(values,active,blocks,1)
    # Constant-frequency control is fitted only on the same training times.
    constants=np.broadcast_to(f[None,:,None],(len(d),len(f),len(times)))
    constant_values=np.broadcast_to(spectrum[None,:,:],constants.shape)
    constant_active=np.broadcast_to(active[:,None,:],constants.shape)
    ctrain,_,_=block_statistics(constant_values,constant_active,blocks,0)
    low=np.min(np.where(active,pred,np.inf),axis=-1)
    high=np.max(np.where(active,pred,-np.inf),axis=-1)
    ctrain=np.where((f>=low[:,None])&(f<=high[:,None]),ctrain,-np.inf)
    ci=np.argmax(ctrain,axis=-1)
    constant=constant_values[row,ci]
    ccheck,_,_=block_statistics(constant,active,blocks,1)
    ctrain=ctrain[row,ci]
    # Time-reversal keeps the same frequencies but deliberately wrong ordering.
    reversed_prediction=pred.copy()
    for i in range(len(pred)):
        reversed_prediction[i,active[i]]=pred[i,active[i]][::-1]
    reversed_values,_=sample_curve(f,spectrum,reversed_prediction,region)
    rtrain,_,_=block_statistics(reversed_values,active,blocks,0)
    rcheck,_,_=block_statistics(reversed_values,active,blocks,1)
    with np.errstate(invalid='ignore'):
        train_margin=train-np.maximum(ctrain,rtrain)
        check_margin=check-np.maximum(ccheck,rcheck)
    valid=np.isfinite(train)&np.isfinite(check)&np.isfinite(train_margin)
    accepted=valid&(train>=2)&(check>=2)&(train_margin>=1)&(check_margin>=1)&(support>=.6)
    return dict(score=np.where(valid,train_margin,-np.inf),source_frequency_hz=np.where(valid,tone,np.nan),
                train_score=train,validation_score=check,constant_score=ccheck,shuffled_score=rcheck,
                support_fraction=support,frequency_span_hz=span,accepted=accepted,valid=valid,
                curve_coverage=active.mean(axis=-1),raw_score=train,check_margin_db=check_margin)
