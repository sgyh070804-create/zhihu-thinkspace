export type PendulumState = {
  angle1: number;
  angle2: number;
  speed1: number;
  speed2: number;
};

export const lengths = [1, 0.86] as const;
export const timeStep = 1 / 240;
export const initialState: PendulumState = {
  angle1: 1.97,
  angle2: 2.35,
  speed1: 0.05,
  speed2: -0.35,
};

const gravity = 9.81;
const mass1 = 1;
const mass2 = 0.8;
const totalMass = mass1 + mass2;

// Solve the two coupled equations of motion for the angular accelerations.
// https://www.myphysicslab.com/pendulum/double-pendulum-en.html
function derivative({ angle1, angle2, speed1, speed2 }: PendulumState): PendulumState {
  const [length1, length2] = lengths;
  const sine = Math.sin(angle1 - angle2);
  const cosine = Math.cos(angle1 - angle2);
  const firstTorque = -totalMass * gravity * Math.sin(angle1) - mass2 * length2 * speed2 ** 2 * sine;
  const secondTorque = -gravity * Math.sin(angle2) + length1 * speed1 ** 2 * sine;
  const denominator = mass1 + mass2 * sine ** 2;

  return {
    angle1: speed1,
    angle2: speed2,
    speed1: (firstTorque - mass2 * cosine * secondTorque) / (length1 * denominator),
    speed2: (totalMass * secondTorque - cosine * firstTorque) / (length2 * denominator),
  };
}

function offset(state: PendulumState, velocity: PendulumState, seconds: number): PendulumState {
  return {
    angle1: state.angle1 + seconds * velocity.angle1,
    angle2: state.angle2 + seconds * velocity.angle2,
    speed1: state.speed1 + seconds * velocity.speed1,
    speed2: state.speed2 + seconds * velocity.speed2,
  };
}

export function advancePendulum(state: PendulumState): PendulumState {
  const a = derivative(state);
  const b = derivative(offset(state, a, timeStep / 2));
  const c = derivative(offset(state, b, timeStep / 2));
  const d = derivative(offset(state, c, timeStep));

  // Fourth-order Runge–Kutta with a fixed step, independent of refresh rate.
  return offset(state, {
    angle1: a.angle1 + 2 * (b.angle1 + c.angle1) + d.angle1,
    angle2: a.angle2 + 2 * (b.angle2 + c.angle2) + d.angle2,
    speed1: a.speed1 + 2 * (b.speed1 + c.speed1) + d.speed1,
    speed2: a.speed2 + 2 * (b.speed2 + c.speed2) + d.speed2,
  }, timeStep / 6);
}
