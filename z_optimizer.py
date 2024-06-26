import numpy as np
from scipy.optimize import minimize
import datetime
import time

# # Constants
# m = 5 # Number of elements in each mixup vector (for simplicity)
# m_prime = 5  # Number of mixup vectors


# # Initial guess (flattened Z)
# Z_init = np.random.rand(m_prime * m)
# Z_init = Z_init.reshape((m_prime, m))
# Z_init /= Z_init.sum(axis=1).flatten()
# Z_init = Z_init.flatten()

# print(Z_init.shape)

# # Uncertainty vector
# u_B = [0.01, 0.1, 0.4, 0.43, 0.8] # np.random.rand(m)

# def cosine_similarity(x, y):
#     """Compute cosine similarity between two vectors."""
#     dot_product = np.dot(x, y)
#     norm_x = np.linalg.norm(x)
#     norm_y = np.linalg.norm(y)
#     return dot_product / (norm_x * norm_y)

# # Objective function
# def objective(Z_flat, alpha = 0.50, beta=0.10):
#     Z = Z_flat.reshape((m_prime, m))
#     uncertainty_term = alpha * np.sum(np.dot(Z, u_B))
#     uncertainty_term = (1.0/(m*m_prime)) * uncertainty_term

#     # diversity_term = 0
#     # for i in range(m_prime):
#     #     for j in range(i + 1, m_prime):
#     #         diversity_term += np.linalg.norm(Z[i] - Z[j]) ** 2
#     # diversity_term = beta * (2.0/(m_prime * (m_prime - 1))) * diversity_term

#     diversity_term = 0
#     for i in range(m_prime):
#         for j in range(i + 1, m_prime):
#             diversity_term += cosine_similarity(Z[i], Z[j])
#     diversity_term = (-1) * beta * (2.0/(m_prime * (m_prime - 1))) * diversity_term

#     gamma = 1-(alpha+beta)
#     penalty_term = gamma * (1.0/(m*m_prime)) * np.sum(Z_flat**2)

#     return -(uncertainty_term + diversity_term) + penalty_term # Negative for maximization

# # Constraint (each row sums to 1)
# def constraint(Z_flat):
#     Z = Z_flat.reshape((m_prime, m))
#     return np.ones(m_prime) - np.sum(Z, axis=1)

# # Constraints dictionary
# cons = ({'type': 'eq', 'fun': constraint})

# # Bounds (Z >= 0)
# bounds = [(0, None) for _ in range(m_prime * m)]

# # Perform the optimization
# print(f"Started @:{datetime.datetime.now()}")
# start = time.time()
# result = minimize(objective, Z_init, method='SLSQP', constraints=cons, bounds=bounds, options={'disp': True})
# end = time.time()
# print(f"Ended @:{datetime.datetime.now()}")
# print(f"Time taken: {end - start} seconds")

# # Output the result
# if result.success:
#     optimal_Z = result.x.reshape((m_prime, m))
#     print("Optimization successful. Optimal Z found:")
#     print(optimal_Z)
#     print(f"Constraint satisfied?: {optimal_Z.sum(axis=1)}")

# else:
#     print("Optimization failed:", result.message)


class z_optimizer():
    def __init__(self, m_prime, m):
        self.m_prime = m_prime
        self.m = m
        
    def cosine_similarity(self, x, y):
        """Compute cosine similarity between two vectors."""
        dot_product = np.dot(x, y)
        norm_x = np.linalg.norm(x)
        norm_y = np.linalg.norm(y)
        return dot_product / (norm_x * norm_y)
    
    def constraint(self, Z_flat):
        Z = Z_flat.reshape((self.m_prime, self.m))
        return np.ones(self.m_prime) - np.sum(Z, axis=1)
    
    def objective(self, Z_flat, u_B, alpha, beta):
        Z = Z_flat.reshape((self.m_prime, self.m))
        uncertainty_term = alpha * np.sum(np.dot(Z, u_B))
        uncertainty_term = (1.0/(self.m*self.m_prime)) * uncertainty_term

        diversity_term = 0
        for i in range(self.m_prime):
            for j in range(i + 1, self.m_prime):
                diversity_term += self.cosine_similarity(Z[i], Z[j])
        diversity_term = (-1) * beta * (2.0/(self.m_prime * (self.m_prime - 1))) * diversity_term

        gamma = 1-(alpha+beta)
        penalty_term = gamma * (1.0/(self.m*self.m_prime)) * np.sum(Z_flat**2)

        return -(uncertainty_term + diversity_term) + penalty_term
    
    def __call__(self, u_B, alpha = 0.10, beta=0.10, print_message = False):
        Z_init = np.random.rand(self.m_prime * self.m)
        bounds = [(0, None) for _ in range(self.m_prime * self.m)]
        cons = ({'type': 'eq', 'fun': self.constraint})
        result = minimize(self.objective, Z_init, args=(u_B, alpha, beta), method='SLSQP', constraints=cons, bounds=bounds) #, options={'disp': True})
        
        if result.success:
            optimal_Z = result.x.reshape((self.m_prime, self.m))
            if print_message:
                print("Optimization successful. Optimal Z found:")
                print(optimal_Z)
                print(f"Constraint satisfied?: {optimal_Z.sum(axis=1)}")
            return optimal_Z

        else:
            raise ValueError("Optimization failed:", result.message)
        
    