"""Exercise importance with independently fitted synthetic ml-engine candidates.

Usage: ``uv run pytest packages/platform/signal-analysis/tests/test_importance_integration.py``.
Only generated data are fitted; tracking is scoped to pytest temporary storage.
"""

# --------------------------------------------------------------------------- #
# Imports and public-engine toy fit helpers
# --------------------------------------------------------------------------- #
import numpy as np
import polars as pl
import pytest

from signal_analysis.importance.mdi import mean_decrease_impurity
from signal_analysis.importance.permutation import permutation_importance
from signal_analysis.importance.single_feature import single_feature_importance

pd = pytest.importorskip("pandas")
pytest.importorskip("ml_engine.training")
from ml_engine.training import (  # noqa: E402
    CandidateConfig,
    MetricConfig,
    PreprocessingConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
    TrainingPipeline,
)
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.linear_model import LinearRegression  # noqa: E402
from sklearn.tree import DecisionTreeClassifier  # noqa: E402


def accuracy(y, p, w):
    return float(np.average(y == (p >= 0.5), weights=w))


def fit(frame, features, tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ENGINE_OUTPUT_ROOT", str(tmp_path / "training"))
    monkeypatch.setenv("ML_ENGINE_PRODUCER", "signal-analysis/synthetic-importance-test")
    config = TrainingConfig(
        feature_cols=tuple(features),
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        target_end_col="target_end",
        split=SplitConfig(kind="purged", min_train_periods=400, eval_periods=200, step_periods=200),
        candidates=tuple(
            CandidateConfig(name=name, estimator=DecisionTreeClassifier(max_depth=3), feature_cols=(name,))
            for name in features
        )
        + (
            CandidateConfig(
                name="joint",
                estimator=RandomForestClassifier(n_estimators=32, max_depth=3, n_jobs=1),
                feature_cols=tuple(features),
            ),
        ),
        metrics=(MetricConfig("accuracy"),),
        selection=SelectionConfig("accuracy", "maximize"),
        random_seed=31,
        task="binary_classification",
        final_refit=False,
        keep_fold_models=True,
    )
    result = TrainingPipeline(config).run(frame)
    # Exercise all candidate OOS rows, not selected output or fitted predictions.
    records = result.candidate_oos.loc[result.candidate_oos["candidate"] != "joint"].copy()
    assert set(records["candidate"]) == set(features)
    assert len(records) == len(features) * sum(fold.eval_count for fold in result.fold_plan)
    for name in features:
        for model in result.fold_models[name].values():
            assert model.n_features_in_ == 1
    for fold in result.fold_plan:
        assert set(fold.train_indices).isdisjoint(fold.eval_indices)
        assert (frame.iloc[list(fold.train_indices)]["target_end"] < fold.eval_start).all()
        for name in features:
            actual = records.loc[(records["fold"] == fold.fold) & (records["candidate"] == name), "row_id"]
            assert set(actual) == set(fold.eval_row_ids)
    rows, models = [], []
    for (feature, fold), group in records.groupby(["candidate", "fold"]):
        model_id = f"{feature}/{fold}"
        models.append((str(fold), model_id, [feature]))
        for record in group.to_dict("records"):
            rows.append(
                (
                    feature,
                    str(fold),
                    model_id,
                    str(record["row_id"]),
                    record["timestamp"].to_pydatetime(),
                    float(record["target"]),
                    float(record["prediction"]),
                    1.0,
                )
            )
    predictions = pl.DataFrame(
        rows,
        schema={
            "feature": pl.String,
            "partition_id": pl.String,
            "model_id": pl.String,
            "observation_id": pl.String,
            "decision_time": pl.Datetime("us", "UTC"),
            "target": pl.Float64,
            "prediction": pl.Float64,
            "sample_weight": pl.Float64,
        },
        orient="row",
    )
    declarations = pl.DataFrame(
        models,
        schema={"partition_id": pl.String, "model_id": pl.String, "feature_columns": pl.List(pl.String)},
        orient="row",
    )
    return result, single_feature_importance(
        predictions,
        model_features=declarations,
        scorer=accuracy,
        score_name="weighted_accuracy",
        greater_is_better=True,
        heldout=True,
        evaluation_provenance="synthetic/public-ml-engine",
    )


def frame_for(features, target):
    n = len(target)
    timestamps = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "row_id": np.arange(n),
            "timestamp": timestamps,
            "target_end": timestamps + pd.Timedelta(days=1),
            "target": target,
            **features,
        }
    )


# --------------------------------------------------------------------------- #
# Seeded mechanism-specific benchmarks
# --------------------------------------------------------------------------- #


def test_informative_redundant_and_noise_oos_importance(tmp_path, monkeypatch):
    rng = np.random.default_rng(91)
    x = rng.normal(size=1200)
    frame = frame_for({"informative": x, "redundant": x.copy(), "noise": rng.normal(size=1200)}, (x > 0).astype(int))
    features = ["informative", "redundant", "noise"]
    fitted, sfi = fit(frame, features, tmp_path, monkeypatch)
    scores = dict(sfi.summary.select("feature", "importance").iter_rows())
    assert scores["informative"] > 0.98
    assert scores["redundant"] > 0.98
    # Six hundred IID test rows: this wide chance band is not an exact ranking.
    assert 0.35 < scores["noise"] < 0.65
    fold = fitted.fold_plan.folds[0]
    forest = fitted.fold_models["joint"][fold.fold]
    trees = pl.DataFrame(
        {
            "tree_id": [str(i) for i in range(len(forest.estimators_))],
            **{
                name: [float(tree.feature_importances_[j]) for tree in forest.estimators_]
                for j, name in enumerate(features)
            },
        }
    )
    mdi = mean_decrease_impurity(trees, feature_columns=features, normalization="conventional")
    assert mdi.summary.filter(pl.col("feature") == "noise")["importance"].item() < 0.1
    selected = frame.iloc[list(fold.eval_indices)]
    heldout = pl.DataFrame(
        {
            "observation_id": [str(value) for value in selected["row_id"]],
            "decision_time": pl.Series(selected["timestamp"].to_list(), dtype=pl.Datetime("us", "UTC")),
            "features_available_at": pl.Series(selected["timestamp"].to_list(), dtype=pl.Datetime("us", "UTC")),
            "target": selected["target"].to_numpy().astype(float),
            "sample_weight": np.ones(len(selected)),
            **{name: selected[name].to_numpy() for name in features},
        }
    )
    mda = permutation_importance(
        heldout,
        feature_columns=features,
        predict=lambda x: fitted.predict_fold(pd.DataFrame(x, columns=features), candidate="joint", fold=fold.fold),
        scorer=accuracy,
        score_name="weighted_accuracy",
        greater_is_better=True,
        model_id="joint/0",
        partition_id="0",
        heldout=True,
        evaluation_provenance="synthetic/public-ml-engine",
        repetitions=12,
        seed=19,
        normalization="raw",
        feature_groups={"shared": ["informative", "redundant"], "noise": ["noise"]},
    )
    scores = dict(mda.summary.select("feature", "importance").iter_rows())
    assert scores["shared"] > 0.35
    assert abs(scores["noise"]) < 0.05


def test_single_feature_scores_miss_pure_interaction(tmp_path, monkeypatch):
    rng = np.random.default_rng(14)
    a = rng.integers(0, 2, 1200)
    b = rng.integers(0, 2, 1200)
    frame = frame_for({"a": a.astype(float), "b": b.astype(float)}, np.bitwise_xor(a, b))
    fitted, sfi = fit(frame, ["a", "b"], tmp_path, monkeypatch)
    assert all(0.35 < score < 0.65 for score in sfi.summary["importance"])
    joint = fitted.candidate_oos.loc[fitted.candidate_oos["candidate"] == "joint"]
    assert np.mean((joint["prediction"] >= 0.5) == joint["target"]) > 0.98


def test_mda_uses_retained_scaling_and_matches_analytical_predictions(tmp_path, monkeypatch):
    monkeypatch.setenv("ML_ENGINE_OUTPUT_ROOT", str(tmp_path / "training"))
    monkeypatch.setenv("ML_ENGINE_PRODUCER", "signal-analysis/scaled-mda-test")
    x = np.arange(8.0)
    frame = frame_for({"x": x}, 2 * x + 3)
    config = TrainingConfig(
        feature_cols=("x",),
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        split=SplitConfig(kind="chronological_holdout", min_train_periods=6, eval_periods=2),
        candidates=(CandidateConfig(name="linear", estimator=LinearRegression()),),
        preprocessing=PreprocessingConfig(scale="standard"),
        metrics=(MetricConfig("rmse"),),
        selection=SelectionConfig("rmse", "minimize"),
        random_seed=31,
        final_refit=False,
        keep_fold_models=True,
    )
    result = TrainingPipeline(config).run(frame)
    fold = result.fold_plan.folds[0]
    selected = frame.iloc[list(fold.eval_indices)]
    heldout = pl.DataFrame(
        {
            "observation_id": [str(value) for value in selected["row_id"]],
            "decision_time": pl.Series(selected["timestamp"].to_list(), dtype=pl.Datetime("us", "UTC")),
            "features_available_at": pl.Series(selected["timestamp"].to_list(), dtype=pl.Datetime("us", "UTC")),
            "target": selected["target"].to_numpy(),
            "sample_weight": [1.0, 3.0],
            "x": selected["x"].to_numpy(),
        }
    )

    def predict(matrix):
        actual = result.predict_fold(pd.DataFrame(matrix, columns=["x"]), candidate="linear", fold=fold.fold)
        # Derive from y=2*x+3, including each permuted matrix, not from OOS or
        # another invocation of the fitted model. Scaling must be applied once.
        np.testing.assert_allclose(actual, 2 * matrix[:, 0] + 3, rtol=0, atol=1e-12)
        return actual

    mda = permutation_importance(
        heldout,
        feature_columns=["x"],
        predict=predict,
        scorer=lambda y, p, w: float(np.average((y - p) ** 2, weights=w)),
        score_name="weighted_mse",
        greater_is_better=False,
        model_id="linear/0",
        partition_id="0",
        heldout=True,
        evaluation_provenance="synthetic/scaled-public-ml-engine",
        repetitions=12,
        seed=19,
        normalization="raw",
    )
    assert mda.raw["baseline_score"].to_numpy() == pytest.approx(0, abs=1e-24)
    # With two evaluation points, swapping x changes both predictions by 2:
    # weighted MSE is exactly 4; the identity permutation leaves it zero.
    for row in mda.raw.iter_rows(named=True):
        expected = 0.0 if row["permutation_indices"] == [0, 1] else 4.0
        assert row["permuted_score"] == pytest.approx(expected, abs=1e-12, rel=0)
