"""Damped least-squares update used by MuJoCo Jacobian IK."""

import numpy as np


def damped_least_squares(
    jacobian: np.ndarray, error: np.ndarray, *, damping: float = 0.05
) -> np.ndarray:
    jacobian = np.asarray(jacobian, dtype=np.float64)
    error = np.asarray(error, dtype=np.float64)
    if jacobian.ndim != 2 or error.shape != (jacobian.shape[0],):
        raise ValueError("jacobian and error dimensions do not match")
    regularizer = (damping**2) * np.eye(jacobian.shape[0])
    return jacobian.T @ np.linalg.solve(jacobian @ jacobian.T + regularizer, error)
