from pathlib import Path

import pandas as pd
from sklearn.datasets import load_iris

FEATURES = ["sepal_length", "sepal_width", "petal_length", "petal_width"]


def generate(path="data/iris.csv"):
    iris = load_iris()
    frame = pd.DataFrame(iris.data, columns=FEATURES)
    frame["target"] = iris.target
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")
    return frame


if __name__ == "__main__":
    generate()
