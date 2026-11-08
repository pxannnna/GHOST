"""Invert the displayed forward curve by integrating spectrogram brightness.

The objective is a descriptive image-match score, not a likelihood. No receiver
coordinate, traced curve, or aircraft identity is supplied as the answer.
"""
import numpy as np
from .model_score import _peak_bins


def sample_curve(frequency, brightness, predicted, frequency_region):
    """Linear frequency interpolation at the actual curve, with no free ridge hops.

    Out-of-band parts contribute zero. Every hypothesis has the same total time
    denominator, so a short intersection with a bright patch gets no advantage.
    """
    f=np.asarray(frequency);p=np.asarray(predicted);b=np.asarray(brightness)
    if b.shape[0]!=len(f) or b.shape[1]!=p.shape[-1]:raise ValueError('Spectrum/curve dimensions differ')
    lo,hi=frequency_region
    active=np.isfinite(p)&(p>=lo)&(p<=hi)&(p>=f[0])&(p<=f[-1])
    u=(np.where(active,p,f[0])-f[0])/(f[1]-f[0]);i=np.floor(u).astype(np.int64)
    i=np.clip(i,0,len(f)-2);fraction=np.clip(u-i,0,1)
    t=np.arange(b.shape[1])
    values=b[i,t]*(1-fraction)+b[i+1,t]*fraction
    return np.where(active,values,0),active


def evaluate_tones(frequency,brightness,factors,tones,region,minimum_span=6,minimum_bend=0,sample_weights=None):
    predicted=factors[:,None,:]*tones[:,:,None]
    values,active=sample_curve(frequency,brightness,predicted,region)
    fraction=active.mean(axis=-1)
    span=np.max(np.where(active,predicted,-np.inf),axis=-1)-np.min(np.where(active,predicted,np.inf),axis=-1)
    good=(np.isfinite(factors).all(axis=-1)&(factors>0).all(axis=-1))[:,None]
    good=good&np.isfinite(tones)&(tones>0)&(fraction>=.3)&(active.sum(axis=-1)>=8)&(span>=minimum_span)
    if minimum_bend>0:
        first=np.argmax(active,axis=-1);last=active.shape[-1]-1-np.argmax(active[...,::-1],axis=-1)
        start=np.take_along_axis(predicted,first[...,None],axis=-1)[...,0];end=np.take_along_axis(predicted,last[...,None],axis=-1)[...,0]
        u=(np.arange(predicted.shape[-1])-first[...,None])/np.maximum(1,last-first)[...,None]
        chord=start[...,None]+(end-start)[...,None]*u
        bend=np.max(np.where(active,abs(predicted-chord),0),axis=-1);good &= bend>=minimum_bend
    if sample_weights is not None:values=values*np.asarray(sample_weights)[:,None,:]
    return np.where(good,100*values.mean(axis=-1),-np.inf),fraction,span


def maximize_intensity(frequency,brightness,factors,region,*,max_tones=64,source_frequencies=None,minimum_span=6,minimum_bend=0,sample_weights=None):
    """Optimize one emitted tone for every candidate geometry on all event audio.

    Coarse proposals dewarp strong peaks at 16 evenly-spaced times. Refine the
    three best tones over +/- 1 Hz in 0.125 Hz steps. This is a bounded numerical
    search, not a proof of the continuous global maximum.
    """
    f=np.asarray(frequency);b=np.asarray(brightness);d=np.atleast_2d(factors)
    if len(f)<5 or b.shape!=(len(f),d.shape[1]) or d.shape[1]<8:raise ValueError('Invalid spectrum shape or too few times')
    if not np.isfinite(b).all() or np.any((b<0)|(b>1)):raise ValueError('Brightness must be finite in [0,1]')
    if not np.allclose(np.diff(f),f[1]-f[0]) or f[1]<=f[0]:raise ValueError('Need uniform increasing frequency bins')
    if source_frequencies is None:
        anchors=np.unique(np.linspace(0,d.shape[1]-1,min(16,d.shape[1])).astype(int))
        proposal=b.copy();proposal[(f<region[0])|(f>region[1])]=-np.inf
        peaks=_peak_bins(f,proposal,anchors,max(1,max_tones//len(anchors)))
        observed=np.where(peaks>=0,f[np.maximum(peaks,0)],np.nan)
        with np.errstate(invalid='ignore',divide='ignore'):
            tones=(observed[None,:,:]/d[:,anchors,None]).reshape(len(d),-1)
    else:
        tones=np.asarray(source_frequencies,dtype=float)
        if tones.ndim==1:tones=np.broadcast_to(tones,(len(d),len(tones)))
        if tones.shape[0]!=len(d):raise ValueError('One tone row per geometry required')
    scores,_,_=evaluate_tones(f,b,d,tones,region,minimum_span,minimum_bend,sample_weights)
    if source_frequencies is None:
        top=np.argsort(scores,axis=1)[:,-min(3,scores.shape[1]):]
        centres=np.take_along_axis(tones,top,axis=1)
        refined=(centres[:,:,None]+np.arange(-1,1.001,.125)[None,None,:]).reshape(len(d),-1)
        # Keep original proposals as well: refinement must never lower the score.
        tones=np.concatenate([np.take_along_axis(tones,top,axis=1),refined],axis=1)
        scores,_,_=evaluate_tones(f,b,d,tones,region,minimum_span,minimum_bend,sample_weights)
    choice=np.argmax(scores,axis=1);rows=np.arange(len(d));tone=tones[rows,choice]
    score=scores[rows,choice];valid=np.isfinite(score)
    _,active=sample_curve(f,b,d*tone[:,None],region)
    return dict(score=score,source_frequency_hz=np.where(valid,tone,np.nan),
                curve_coverage=np.where(valid,active.mean(axis=-1),0),valid=valid)
