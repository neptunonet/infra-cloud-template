"""Trains a tiny classifier at BUILD TIME (inside the Docker image), not at
runtime. This is the pattern used from class 5 onward: weights live outside
the app code, baked into the image (or, in a fancier setup, pulled from
object storage on startup). Here we keep it simple: the model file ends up
next to the server code inside the image.
"""

from __future__ import annotations

import joblib
from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression

MODEL_PATH = "model.joblib"


def main() -> None:
    data = load_iris()
    clf = LogisticRegression(max_iter=200)
    clf.fit(data.data, data.target)
    joblib.dump({"model": clf, "target_names": list(data.target_names)}, MODEL_PATH)
    print(f"Trained iris classifier, saved to {MODEL_PATH}")


if __name__ == "__main__":
    main()
