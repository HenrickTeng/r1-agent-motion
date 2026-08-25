#include "locomotion_policy.hpp"

#include <algorithm>
#include <cmath>

namespace r1::motion {
namespace {
constexpr double kPi = 3.14159265358979323846;
}

double NormalizeAngle(double radians) {
  while (radians > kPi) radians -= 2 * kPi;
  while (radians < -kPi) radians += 2 * kPi;
  return radians;
}

double ComputeTurnRate(double yaw_error_radians, double maximum_rate_rad_s) {
  const double proportional = 1.2 * NormalizeAngle(yaw_error_radians);
  const double limited = std::clamp(proportional, -maximum_rate_rad_s, maximum_rate_rad_s);
  if (std::abs(limited) < 0.04 && std::abs(yaw_error_radians) > 0.026) {
    return std::copysign(0.04, limited);
  }
  return limited;
}

bool TurnReached(double yaw_error_radians, double tolerance_degrees) {
  return std::abs(NormalizeAngle(yaw_error_radians)) <= tolerance_degrees * kPi / 180.0;
}

}  // namespace r1::motion
