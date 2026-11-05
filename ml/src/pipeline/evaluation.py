"""Score evidenced saved forecasts, separately from hindsight reconstruction."""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from src.pipeline.publish import PublicationError, _validate_selection, select_final


def evaluate_saved(data_root: Path, results: pd.DataFrame) -> dict:
    samples = {'initial': [], 'final': []}
    excluded = []
    for path in sorted((Path(data_root) / 'prediction_snapshots').glob('*/feed.json')):
        try:
            feed = json.loads(path.read_text(encoding='utf-8'))
            event = feed['event']
            if results.empty:
                continue
            race = results[(results.season == event['season']) & (results['round'] == event['round'])]
            top = race[race.position.isin([1, 2, 3])].sort_values('position')
            if len(top) != 3 or top.position.nunique() != 3 or top.driver_id.nunique() != 3:
                continue
            selections = {'initial': feed.get('initial'), 'final': None}
            final_path = path.with_name('final.json')
            if final_path.exists():
                final = json.loads(final_path.read_text(encoding='utf-8'))
                receipt = final.get('publication')
                if receipt and select_final([receipt], final['cutoff_at'], event=event) == receipt:
                    for key in ('current', 'previous', 'initial'):
                        selection = feed.get(key)
                        if selection and selection['publication'] == receipt:
                            selections['final'] = selection
                            break
            for mode, selection in selections.items():
                if selection is None:
                    continue
                _validate_selection(selection, event)
                prediction = selection['prediction']
                field = 'realGridPodium' if prediction['mode'] == 'actual_qualifying' else 'preQualifyingPodium'
                predicted = sorted(prediction['forecast'][field], key=lambda row: row['rank'])[:3]
                ids = [row['driver_id'] for row in predicted]
                samples[mode].append({'race_id': feed['current_event_id'],
                    'prediction_id': prediction['prediction_id'],
                    'podium_hits': len(set(ids) & set(top.driver_id)),
                    'winner_hit': int(ids[0] == top.iloc[0].driver_id)})
        except (PublicationError, ValueError, KeyError, TypeError, OSError) as exc:
            excluded.append({'race_id': path.parent.name, 'reason': str(exc)})
    output = {'kind': 'confirmed_saved_forecast_evaluation', 'excluded': excluded}
    for mode, rows in samples.items():
        count = len(rows)
        output[mode] = {'races': count,
            'podium_hit_rate': sum(r['podium_hits'] for r in rows) / (3 * count) if count else None,
            'winner_accuracy': sum(r['winner_hit'] for r in rows) / count if count else None,
            'samples': rows}
    return output
