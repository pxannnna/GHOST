"""Conservative streaming tonal-ridge proposals, never aircraft identifications."""
import numpy as np


class RidgeDetector:
    def __init__(self, rate, hop_s=.5):
        self.rate=rate;self.hop=hop_s;self.tracks=[];self.serial=0;self.proposals={}

    def update(self, sample, frequencies, db):
        keep=(frequencies>=40)&(frequencies<=1000)
        f=frequencies[keep];power=db[keep]
        if not np.isfinite(power).all():
            self.tracks=[];return []
        width=max(5,int(round(16/(f[1]-f[0])))|1)
        background=np.convolve(np.pad(power,width//2,mode='edge'),np.ones(width)/width,mode='valid')
        strength=power-background
        peaks=np.where((power[1:-1]>power[:-2])&(power[1:-1]>=power[2:])&
                       (strength[1:-1]>10)&(power[1:-1]>-80))[0]+1
        peaks=sorted(peaks,key=lambda i:strength[i],reverse=True)
        selected=[]
        for i in peaks:
            if all(abs(f[i]-f[j])>1 for j in selected):selected.append(i)
            if len(selected)>=60:break
        used=set();alive=[];updated=[]
        # Prefer established tracks when tones intersect.
        for track in sorted(self.tracks,key=lambda t:len(t['points']),reverse=True):
            points=track['points'];last=points[-1];dt=(sample-last[0])/self.rate
            if dt>2:continue
            slope=0
            if len(points)>=5:
                slope=np.clip((last[1]-points[-5][1])/((last[0]-points[-5][0])/self.rate),-6,2)
            expected=last[1]+slope*dt
            choices=[i for i in selected if i not in used and abs(f[i]-expected)<=max(1,3*dt)
                     and -6*dt-.5<=f[i]-last[1]<=2*dt+.5]
            if choices:
                i=min(choices,key=lambda j:abs(f[j]-expected));used.add(i)
                points.append((int(sample),float(f[i]),float(strength[i])))
                track['points']=points[-360:]
                proposal=self.propose(track)
                if proposal:
                    self.proposals[track['id']]=proposal;updated.append(proposal)
            alive.append(track)
        for i in selected:
            if i not in used:
                self.serial+=1
                alive.append(dict(id=f'tone-v2-{sample}-{self.serial}',points=[(int(sample),float(f[i]),float(strength[i]))]))
        self.tracks=alive[:100]
        # Bounded retained proposal list; archived JSON remains on disk.
        self.proposals=dict(list(self.proposals.items())[-50:])
        return updated

    def propose(self,track):
        points=np.array(track['points']);t=(points[:,0]-points[0,0])/self.rate;f=points[:,1]
        if len(t)<55 or t[-1]<30 or t[-1]>180:return None
        span=float(np.median(f[:5])-np.median(f[-5:]))
        if span<6 or span>300:return None
        slope,intercept=np.polyfit(t,f,1)
        fitted=slope*t+intercept
        r2=1-np.sum((f-fitted)**2)/max(np.sum((f-f.mean())**2),1e-9)
        descent=float(np.mean(np.diff(f)<=.5))
        coverage=len(t)*self.hop/(t[-1]+self.hop)
        if not (-6<slope<-.05 and r2>.85 and descent>.9 and coverage>.9 and np.median(points[:,2])>=14):return None
        indices=np.unique(np.linspace(0,len(points)-1,min(30,len(points))).astype(int))
        return dict(candidate_id=track['id'],start_sample=int(points[0,0]),end_sample=int(points[-1,0])+1,
            ridge=[dict(sample=int(points[i,0]),frequency_hz=float(points[i,1]),sigma_hz=1.0) for i in indices],
            measured_peaks=[dict(sample=int(row[0]),frequency_hz=float(row[1]),prominence_db=float(row[2])) for row in points],
            detector_version=2,
            duration_s=float(t[-1]),frequency_drop_hz=span,linear_r2=float(r2),coverage=float(coverage),
            median_prominence_db=float(np.median(points[:,2])),status='unreviewed_tonal_candidate',
            caveat='Descending tone heuristic, not proof of aircraft or Doppler. Review the ridge before matching.')
