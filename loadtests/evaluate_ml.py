"""Local held-out model quality check using reproducible synthetic traffic features."""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report

rng = np.random.default_rng(23)
normal_train = np.column_stack([rng.normal(1.2, .45, 1200), rng.beta(1, 35, 1200), rng.normal(1.1, .6, 1200), rng.normal(850, 250, 1200), rng.normal(900, 350, 1200)])
normal_test = np.column_stack([rng.normal(1.2, .45, 500), rng.beta(1, 35, 500), rng.normal(1.1, .6, 500), rng.normal(850, 250, 500), rng.normal(900, 350, 500)])
bot_test = np.column_stack([rng.normal(30, 8, 100), rng.beta(1, 4, 100), rng.normal(.15, .1, 100), rng.normal(35, 10, 100), rng.normal(400, 150, 100)])
X = np.vstack([normal_test, bot_test])
y = np.array([0] * len(normal_test) + [1] * len(bot_test))
model = IsolationForest(n_estimators=200, contamination=.08, random_state=7).fit(normal_train)
pred = (model.predict(X) == -1).astype(int)
print(classification_report(y, pred, target_names=["normal", "bot"], digits=3))
