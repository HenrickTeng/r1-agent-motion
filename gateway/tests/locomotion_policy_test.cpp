#include "locomotion_policy.hpp"

#include <gtest/gtest.h>

TEST(LocomotionPolicy, WrapsYawAcrossPi) {
  EXPECT_NEAR(r1::motion::NormalizeAngle(3.2), -3.083185307, 1e-8);
  EXPECT_NEAR(r1::motion::NormalizeAngle(-3.2), 3.083185307, 1e-8);
}

TEST(LocomotionPolicy, ClampsAndSlowsTurnRate) {
  EXPECT_DOUBLE_EQ(r1::motion::ComputeTurnRate(1.0), 0.2);
  EXPECT_NEAR(r1::motion::ComputeTurnRate(0.05), 0.06, 1e-9);
  EXPECT_TRUE(r1::motion::TurnReached(0.01));
  EXPECT_FALSE(r1::motion::TurnReached(0.1));
}
