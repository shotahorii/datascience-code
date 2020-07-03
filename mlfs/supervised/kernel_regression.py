"""
Kernel Regression

References:
"""

# Author: Shota Horii <sh.sinker@gmail.com>

import math
import numpy as np

from mlfs.utils.preprocessing import StandardScaler
from mlfs.utils.solvers import LeastSquareGD
from mlfs.utils.kernels import LinearKernel, PolynomialKernel, RBFKernel, SigmoidKernel
from mlfs.supervised.base_classes import Regressor

class KernelRegression(Regressor):

    def __init__(self, kernel='rbf', kernel_params={}, solver='pinv', alpha=0, max_iterations=1000, tol=1e-4, learning_rate=None):
        self.solver = solver
        self.alpha = alpha
        self.max_iterations = max_iterations
        self.tol = tol
        self.learning_rate = learning_rate

        self.scaler = StandardScaler()

        self.X = None
        self.w = None

        if kernel == 'rbf':
            self.kernel = RBFKernel(**kernel_params)
        elif kernel == 'linear':
            self.kernel = LinearKernel(**kernel_params)
        elif kernel == 'polynomial':
            self.kernel = PolynomialKernel(**kernel_params)
        elif kernel == 'sigmoid':
            self.kernel = SigmoidKernel(**kernel_params)
        else:
            raise ValueError('Invalid Kernel.')

    def fit(self, X, y):
        X = self.scaler.fit(X).transform(X)
        self.X = X

        N = X.shape[0]
        K = np.zeros((N, N))
        for i, xi in enumerate(X):
            for j, xj in enumerate(X):
                K[i,j] = self.kernel(xi, xj)

        if self.solver == 'pinv':
            self.w = np.linalg.pinv(K + self.alpha * np.eye(N)) @ y
        elif self.solver == 'gradient_descent':
            gd = LeastSquareGD(self.alpha, self.max_iterations, self.tol, self.learning_rate)
            self.w = gd.solve(K, y, has_intercept=False)

        return self

    def predict(self, X):
        X = self.scaler.transform(X)

        N = self.X.shape[0]
        M = X.shape[0]
        K = np.zeros((M, N))
        for i, xi in enumerate(X):
            for j, xj in enumerate(self.X):
                K[i,j] = self.kernel(xi, xj)

        return np.dot(self.w, K.T)


