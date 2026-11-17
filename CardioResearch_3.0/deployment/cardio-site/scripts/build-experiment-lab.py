"""Run the separate bounded experiment protocol; write aggregate results only.

Example: python scripts/build-experiment-lab.py --project C:/path/CardioResearch
No original model, research report or dataset is modified.
"""
import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'data' / 'experiment-lab.json')
    parser.add_argument('--datasets', nargs='+', choices=['uci', 'brfss'], default=['uci', 'brfss'])
    parser.add_argument('--algorithms', nargs='+', choices=['logistic_regression', 'random_forest'], default=['logistic_regression', 'random_forest'])
    parser.add_argument('--seed', type=int, default=20261109)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project.resolve()))
    source = Path(__file__).resolve().parents[1] / 'python' / 'cardio' / 'experiment_lab.py'
    spec = importlib.util.spec_from_file_location('cardio.experiment_lab', source)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    runs = []
    for dataset in args.datasets:
        for algorithm in args.algorithms:
            print(f'Start {dataset} {algorithm}', flush=True)
            def progress(percent, stage):
                if stage.startswith('learning:') or stage == 'finalizing':
                    print(f'{percent}% {stage}', flush=True)
            result = module.run_experiment(args.project, {'dataset': dataset, 'algorithm': algorithm, 'seed': args.seed}, progress=progress)
            runs.append(result)
            # Write after each completed model so interruption retains measured work.
            payload = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'runs': runs,
                'runner': {'available': False, 'local': False, 'available_datasets': [], 'algorithms': list(module.ALGORITHMS),
                           'active_job': None, 'recent_jobs': [], 'reason': 'Run experiments in the local Python application'}}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_suffix('.partial.json')
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
            temporary.replace(args.output)
            print(f'Completed in {result["duration_seconds"]:.1f}s; n={result["n"]}; AP={result["baseline"]["average_precision"]["mean"]:.6f}', flush=True)
    print(json.dumps({'output': str(args.output), 'completed_runs': len(runs)}), flush=True)


if __name__ == '__main__':
    main()
