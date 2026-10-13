// Class 6/8: quick load test used to trigger the HPA on servicio-patron
// and model. Run with (k6 installed, or `make loadtest`, which falls back
// to the grafana/k6 docker image):
//   k6 run loadtest/k6-script.js
//   k6 run -e TARGET=model -e MODEL_URL=http://localhost:8081 loadtest/k6-script.js
// To really move the HPA run it INSIDE the cluster (loadtest/k6-job.yaml):
// a port-forward sends every request to a single pod.
//
// Env vars (all optional, sensible localhost defaults -- no hardcoded
// cluster hostnames):
//   TARGET                 "servicio-patron" (default) | "model"
//   SERVICIO_PATRON_URL    default http://localhost:8080
//   MODEL_URL              default http://localhost:8081
//   SLEEP                  seconds each virtual user waits between iterations
//                          (default 1). The model is so light that it needs
//                          about 0.05 to push the HPA past 60% CPU.
//   PEAK_VUS               virtual users at the peak (default 30)
import http from "k6/http";
import { check, sleep } from "k6";

const SLEEP = Number(__ENV.SLEEP || 1);
const PEAK_VUS = Number(__ENV.PEAK_VUS || 30);

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "30s", target: Math.max(1, Math.round(PEAK_VUS / 3)) },
        { duration: "1m", target: PEAK_VUS }, // sustained load to trip a 60-70% CPU HPA target
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<2000"],
  },
};

const TARGET = __ENV.TARGET || "servicio-patron";
const SERVICIO_PATRON_URL = __ENV.SERVICIO_PATRON_URL || "http://localhost:8080";
const MODEL_URL = __ENV.MODEL_URL || "http://localhost:8081";

export default function () {
  if (TARGET === "model") {
    const payload = JSON.stringify({ features: [5.1, 3.5, 1.4, 0.2] });
    const res = http.post(`${MODEL_URL}/predict`, payload, {
      headers: { "Content-Type": "application/json" },
    });
    check(res, { "predict 200": (r) => r.status === 200 });
  } else {
    const res = http.get(`${SERVICIO_PATRON_URL}/`);
    check(res, { "root 200": (r) => r.status === 200 });
  }

  sleep(SLEEP);
}
