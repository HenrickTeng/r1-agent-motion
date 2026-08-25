#pragma once

namespace r1::motion {

double NormalizeAngle(double radians);
double ComputeTurnRate(double yaw_error_radians, double maximum_rate_rad_s = 0.2);
bool TurnReached(double yaw_error_radians, double tolerance_degrees = 1.5);

}  // namespace r1::motion
