"""Rank aircraft/receiver hypotheses against an observed spectrogram.

Run `python -m aircraft_audio.identify --demo` for a synthetic smoke test.
No known receiver or aircraft identity is supplied to rank_candidates.
"""
import argparse
import json
import numpy as np
from .geometry import Frame, Track, ecef, received_curve
from .model_score import local_contrast
from .sustained_match import fit_sustained


def clear_path(receivers, sources):
    axes = np.array([6378137., 6378137., 6356752.314245])
    r = receivers[:, None, :] / axes
    d = sources / axes - r
    u = np.clip(-np.sum(r*d, axis=-1) / np.maximum(np.sum(d*d, axis=-1), 1e-30), 0, 1)
    return np.sum((r+u[..., None]*d)**2, axis=-1) >= 1-1e-10


def rank_candidates(frequency, db, times, utc_start, flights, points,
                    height_m=100., sound_speed=343., max_range_m=40000.,
                    band=(80., 550.), max_gap_s=25.):
    """Return training-score-ranked hypotheses, including rejection flags.

    frequency: uniform frequency-bin centres in Hz.
    db: power spectrogram [frequency, time], in dB.
    times: increasing spectrogram window-centre seconds relative to utc_start.
    flights: {identity: normalized ADS-B record list}; altitude_m must be WGS84
             ellipsoid height, not unconverted barometric altitude.
    points: candidate receiver latitude/longitude array, shape [N,2].
    height_m: common receiver ellipsoid height (use terrain-aware heights in a
              full deployment). Empty/unsupported hypotheses yield no result.
    """
    frequency = np.asarray(frequency, float)
    times = np.asarray(times, float)
    points = np.asarray(points, float)
    if points.ndim != 2 or points.shape[1] != 2 or not len(points):
        raise ValueError('Expected nonempty Nx2 receiver latitude/longitude grid')
    if not np.isfinite(points).all() or np.any(abs(points[:, 0]) > 90) or np.any(abs(points[:, 1]) > 180):
        raise ValueError('Invalid receiver coordinates')
    if not np.isfinite(db).all() or len(times)<2 or np.any(np.diff(times)<=0):
        raise ValueError('Finite spectra and increasing frame times required')
    if sound_speed<=0 or max_range_m<=0:
        raise ValueError('Sound speed and range must be positive')
    evidence = local_contrast(frequency, db)
    frame = Frame(float(points[:, 0].mean()), float(points[:, 1].mean()))
    results = []
    for identity, records in flights.items():
        if len(records)<2:
            continue
        track = Track(records, frame, max_gap=max_gap_s)
        for first in range(0, len(points), 4):
            group = points[first:first+4]
            receivers = frame.xyz(group[:, 0], group[:, 1], height_m)
            factor, emission, distance, valid = received_curve(
                track, receivers, times+utc_start, c=sound_speed)
            source, _, _ = track.at(emission)
            valid &= clear_path(ecef(group[:, 0], group[:, 1], height_m),
                                source @ frame.rotation + frame.origin)
            supported = valid.all(axis=1) & (distance.min(axis=1)<=max_range_m)
            for i in np.flatnonzero(supported):
                fit = fit_sustained(frequency, evidence, factor[i:i+1], times, band)
                if not bool(fit['valid'][0]):
                    continue
                results.append(dict(aircraft=str(identity), candidate_index=first+int(i),
                    latitude=float(group[i,0]), longitude=float(group[i,1]),
                    score_db=float(fit['score'][0]), accepted=bool(fit['accepted'][0]),
                    source_frequency_hz=float(fit['source_frequency_hz'][0]),
                    validation_margin_db=float(fit['check_margin_db'][0]),
                    support_fraction=float(fit['support_fraction'][0]),
                    minimum_slant_range_m=float(distance[i].min())))
    return sorted(results, key=lambda r:r['score_db'], reverse=True)


def demo():
    """Explicit synthetic spectrum; not a microphone or UK field result."""
    lat, lon = 55., -3.
    points = np.array([[lat,lon], [lat+.02,lon], [lat-.02,lon],
                       [lat,lon+.035], [lat,lon-.035]])
    records = [dict(time_position=float(t), latitude=lat+.006,
        longitude=lon+100*(t-1050)/(111320*np.cos(np.radians(lat))),
        altitude_m=1800.) for t in np.arange(850., 1251., 5.)]
    frame = Frame(lat,lon)
    times = np.arange(0.,100.,.5)
    factor, _, _, valid = received_curve(Track(records,frame),
        frame.xyz(lat,lon,100.), 1000+times)
    assert valid.all()
    frequency = np.arange(80.,550.5,.5)
    db = np.random.default_rng(4).normal(-85,1,(len(frequency),len(times)))
    db += 22*np.exp(-.5*((frequency[:,None]-220*factor[0])/.7)**2)
    distractor = [dict(r, time_position=r['time_position']+35,
                       latitude=r['latitude']+.04) for r in records]
    ranking = rank_candidates(frequency,db,times,1000.,
        {'SYNTHETIC-AIRCRAFT':records,'SYNTHETIC-DISTRACTOR':distractor},points)
    return dict(mode='synthetic demonstration',
        expected_receiver=dict(latitude=lat,longitude=lon),
        best_supported=next((r for r in ranking if r['accepted']),None),
        ranking=ranking,
        limitation='Heuristic spectral matching, not calibrated confidence or demonstrated real-world accuracy.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',action='store_true')
    parser.add_argument('--spectrum',help='NPZ with frequency, times, db and scalar utc_start')
    parser.add_argument('--flights',help='JSON object mapping flight identities to normalized records')
    parser.add_argument('--grid',help='JSON array of [latitude,longitude] candidates')
    parser.add_argument('--output',help='Optional JSON output path')
    args=parser.parse_args()
    if args.demo:
        result=demo()
    else:
        if not all([args.spectrum,args.flights,args.grid]):
            parser.error('Use --demo, or provide --spectrum, --flights and --grid')
        with np.load(args.spectrum,allow_pickle=False) as z:
            with open(args.flights) as f:flights=json.load(f)
            with open(args.grid) as f:points=json.load(f)
            ranking=rank_candidates(z['frequency'],z['db'],z['times'],float(z['utc_start']),flights,points)
        result=dict(ranking=ranking,best_supported=next((r for r in ranking if r['accepted']),None),
            score_kind='descriptive spectral contrast, not probability')
    content=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.output:
        with open(args.output,'w') as f:f.write(content)
    else:print(content,end='')

if __name__=='__main__':main()
