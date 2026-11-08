"""WGS84 ECEF/ENU geometry; altitude is assumed ellipsoid metres throughout."""
import numpy as np


def ecef(latitude, longitude, height):
    lat, lon = np.radians(latitude), np.radians(longitude)
    a, e2 = 6378137.0, 6.69437999014e-3
    n = a / np.sqrt(1 - e2 * np.sin(lat)**2)
    return np.stack(((n + height) * np.cos(lat) * np.cos(lon),
                     (n + height) * np.cos(lat) * np.sin(lon),
                     (n * (1 - e2) + height) * np.sin(lat)), axis=-1)


class Frame:
    def __init__(self, latitude=55.935, longitude=-3.225):
        lat, lon = np.radians([latitude, longitude])
        self.origin = ecef(latitude, longitude, 0)
        self.rotation = np.array([[-np.sin(lon), np.cos(lon), 0],
            [-np.sin(lat)*np.cos(lon), -np.sin(lat)*np.sin(lon), np.cos(lat)],
            [np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)]])

    def xyz(self, latitude, longitude, height):
        return (ecef(latitude, longitude, height) - self.origin) @ self.rotation.T


class Track:
    def __init__(self, records, frame, max_gap=15):
        records = sorted({float(r['time_position']): r for r in records}.values(),
                         key=lambda r: r['time_position'])
        if len(records) < 2:
            raise ValueError('At least two track positions required')
        self.times = np.array([r['time_position'] for r in records])
        self.positions = frame.xyz(np.array([r['latitude'] for r in records]),
            np.array([r['longitude'] for r in records]), np.array([r['altitude_m'] for r in records]))
        self.max_gap = max_gap
        self.dt = np.diff(self.times)
        self.velocities = np.diff(self.positions, axis=0) / self.dt[:, None]
        if not np.isfinite(self.positions).all():
            raise ValueError('Non-finite track position')

    def at(self, times):
        index = np.clip(np.searchsorted(self.times, times, side='right') - 1, 0, len(self.dt)-1)
        velocity = self.velocities[index]
        position = self.positions[index] + (times-self.times[index])[..., None]*velocity
        valid = ((times >= self.times[0]) & (times <= self.times[-1]) &
                 (self.dt[index] <= self.max_gap) & (np.linalg.norm(velocity, axis=-1) < 330))
        return position, velocity, valid


def received_curve(track, receivers, receive_times, delta=0, c=343):
    """Return Doppler multiplier, emission times, ranges and validity (N x T).

    Solve retarded time using Newton iterations with piecewise-linear velocity.
    Unsupported final emission times/gaps are rejected, never extrapolated as evidence.
    """
    receivers = np.atleast_2d(receivers)
    arrival = np.asarray(receive_times, dtype=float)[None, :] + delta
    te = np.broadcast_to(arrival, (len(receivers), arrival.shape[1])).copy()
    for _ in range(20):
        p, v, valid = track.at(te)
        d = p - receivers[:, None, :]
        r = np.maximum(np.linalg.norm(d, axis=-1), 1e-6)
        rate = np.sum(d*v, axis=-1)/r
        derivative = 1 + rate/c
        residual = te + r/c-arrival
        if np.max(np.abs(residual)) < 1e-6:
            break
        te -= np.clip(residual / np.maximum(derivative, .05), -300, 300)
    p, v, valid = track.at(te)
    d = p - receivers[:, None, :]
    r = np.maximum(np.linalg.norm(d, axis=-1), 1e-6)
    rate = np.sum(d*v, axis=-1)/r
    valid &= (np.abs(te+r/c-arrival) < 1e-4) & (1+rate/c > 0)
    return 1/(1+rate/c), te, r, valid


def cpa(track, receiver, c=343):
    d = track.positions[:-1] - receiver
    v = track.velocities
    t = np.clip(-np.sum(d*v, axis=1)/np.maximum(np.sum(v*v, axis=1), 1e-12), 0, track.dt)
    ranges = np.linalg.norm(d+t[:, None]*v, axis=1)
    ranges[track.dt > track.max_gap] = np.inf
    i = int(np.argmin(ranges))
    if not np.isfinite(ranges[i]):
        return None
    emission = float(track.times[i]+t[i])
    return dict(emission_utc_epoch=emission, arrival_utc_epoch=emission+float(ranges[i])/c,
                slant_range_m=float(ranges[i]))


class SmoothTrack(Track):
    """C1 flight trajectory from local quadratic fits and cubic Hermite joins.

    Explicit simulation/analysis option; raw archive positions are never changed.
    No smoothing across disconnected segments. Position adjustments are recorded.
    """
    def __init__(self, records, frame, max_gap=15, smoothing_s=30):
        super().__init__(records, frame, max_gap)
        raw=self.positions.copy();positions=[];tangents=[]
        for t in self.times:
            indices=np.flatnonzero(np.abs(self.times-t)<=smoothing_s)
            if len(indices)<5:indices=np.argsort(np.abs(self.times-t))[:min(5,len(self.times))]
            x=self.times[indices]-t
            weights=np.exp(-.5*(x/max(smoothing_s,1))**2)
            design=np.column_stack([np.ones(len(x)),x,x*x])
            coeff=np.linalg.lstsq(design*weights[:,None],raw[indices]*weights[:,None],rcond=None)[0]
            positions.append(coeff[0]);tangents.append(coeff[1])
        self.positions=np.array(positions);self.tangents=np.array(tangents)
        self.velocities=np.diff(self.positions,axis=0)/self.dt[:,None]
        self.smoothing_adjustments_m=np.linalg.norm(self.positions-raw,axis=1)

    def at(self,times):
        times=np.asarray(times);i=np.clip(np.searchsorted(self.times,times,side='right')-1,0,len(self.dt)-1)
        dt=self.dt[i];u=(times-self.times[i])/dt
        # Clamp outside coverage for Newton's initial estimate; valid remains false.
        u=np.clip(u,0,1);u=u[...,None];dt=dt[...,None]
        p0,p1=self.positions[i],self.positions[i+1];v0,v1=self.tangents[i],self.tangents[i+1]
        p=(2*u**3-3*u**2+1)*p0+(u**3-2*u**2+u)*dt*v0+(-2*u**3+3*u**2)*p1+(u**3-u**2)*dt*v1
        v=(6*u*u-6*u)/dt*p0+(3*u*u-4*u+1)*v0+(-6*u*u+6*u)/dt*p1+(3*u*u-2*u)*v1
        valid=(times>=self.times[0])&(times<=self.times[-1])&(self.dt[i]<=self.max_gap)&(np.linalg.norm(v,axis=-1)<330)
        return p,v,valid


class KinematicTrack(SmoothTrack):
    """C2 cubic B-spline trajectory; velocity is its analytic derivative.

    Used by the shape matcher. Uniform 5 s spline knots avoid subsecond report
    spacing amplifying mismatches between independently fitted node positions
    and tangents. A curvature penalty regularizes position noise. Raw positions
    and fit residuals remain available for inspection; large gaps are rejected.
    """
    def __init__(self, records, frame, max_gap=25, knot_s=5., penalty=1.):
        Track.__init__(self,records,frame,max_gap)
        raw=self.positions.copy();raw_times=self.times.copy()
        if np.any(np.diff(raw_times)>max_gap):raise ValueError('Split raw track gaps before spline fitting')
        origin=np.floor(raw_times[0]/knot_s)*knot_s
        end=int(np.floor((raw_times[-1]-origin)/knot_s));count=end+4
        def basis(times,derivative=False):
            u=(np.asarray(times)-origin)/knot_s;i=np.floor(u).astype(int);u=u-i
            if derivative:
                values=np.column_stack([-.5*(1-u)**2,1.5*u*u-2*u,-1.5*u*u+u+.5,.5*u*u])/knot_s
            else:
                values=np.column_stack([(1-u)**3,3*u**3-6*u*u+4,-3*u**3+3*u*u+3*u+1,u**3])/6
            a=np.zeros((len(u),count));a[np.arange(len(u))[:,None],i[:,None]+np.arange(4)]=values
            return a
        a=basis(raw_times);d2=np.diff(np.eye(count),n=2,axis=0)
        # Time weighting prevents a burst of repeated reports from dominating.
        weights=np.clip(np.r_[np.diff(raw_times),np.median(np.diff(raw_times))]/knot_s,.001,2)
        relative=raw-raw[0]
        normal=a.T@(weights[:,None]*a)+penalty*(d2.T@d2)+1e-8*np.eye(count)
        coeff=np.linalg.solve(normal,a.T@(weights[:,None]*relative))
        fitted=a@coeff+raw[0]
        self.raw_times=raw_times;self.raw_positions=raw
        self.smoothing_adjustments_m=np.linalg.norm(fitted-raw,axis=1)
        knots=origin+np.arange(end+1)*knot_s
        self.times=np.unique(np.r_[raw_times[0],knots[(knots>raw_times[0])&(knots<raw_times[-1])],raw_times[-1]])
        self.positions=basis(self.times)@coeff+raw[0];self.tangents=basis(self.times,True)@coeff
        self.dt=np.diff(self.times);self.velocities=np.diff(self.positions,axis=0)/self.dt[:,None]
        self.knot_s=knot_s;self.penalty=penalty
