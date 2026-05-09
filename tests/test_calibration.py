from promptgate.calibrate import JudgeCalibrator
from promptgate.config import Config


def test_judge_calibration_cohen_kappa():
    calibrator = JudgeCalibrator()
    calib_file = Config.DATASETS_DIR / "calibration_set.jsonl"
    
    result = calibrator.run_calibration(calibration_path=calib_file, metric_name="tone_and_empathy")
    
    assert result.total_samples == 50
    # Cohen's kappa should indicate substantial agreement (> 0.6)
    assert result.cohen_kappa >= 0.60
    assert result.exact_agreement_rate >= 0.60
    assert result.within_one_agreement_rate >= 0.85
