// Prueba de carga de la API lluvia (Trabajo Final, consigna 4): lotes de tramos contra POST /predict.
// Corre como Job dentro del clúster (loadtest/lluvia-grilla.sh lo lanza): pega al Service, así la carga se reparte
// entre todas las réplicas (un port-forward la manda a un solo pod).
//
// Modelo cerrado: VUS usuarios virtuales mandan un pedido, esperan la respuesta y mandan el siguiente, sin pausa.
// «Carga 1, 2, 5 y 10» de la consigna = VUS 1, 2, 5 y 10 pedidos simultáneos.
//
// Variables (todas opcionales):
//   URL       por defecto http://lluvia:8083
//   FILAS     tramos por pedido (156 = mediana real de un pedido de Clima Rutero; 4810 = un pedido grande)
//   VUS       pedidos simultáneos (por defecto 1)
//   DURACION  por defecto 60s
//   CLAVE     X-API-Key, si la API pide clave
//
// Lotes sintéticos con la mezcla de una ruta real: ~60 % de tramos a <= 10 km de una estación entrenada (responde el
// modelo), ~30 % en la región entrenada y ~10 % en zona no vista (responde la tabla); ~5 % con anticipación mayor a
// 6 h y ~3 % con un modelo numérico faltante. Semilla fija: todas las corridas mandan los mismos lotes.
import http from "k6/http";
import { check } from "k6";

const URL = __ENV.URL || "http://lluvia:8083";
const FILAS = Number(__ENV.FILAS || 156);
const VUS = Number(__ENV.VUS || 1);
const DURACION = __ENV.DURACION || "60s";
const VARIANTES = 8; // lotes distintos que rota cada usuario virtual

export const options = {
  scenarios: { carga: { executor: "constant-vus", vus: VUS, duration: DURACION } },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
  thresholds: { http_req_failed: ["rate<0.01"] },
};

// Estaciones del modelo activo (metadata de v20261112_073004) y dos lugares sin estación entrenada cerca.
const ESTACIONES = [
  [-32.918, -60.782], [-31.712, -60.812], [-34.5606, -58.7896], [-34.972, -57.895],
  [-34.676, -58.643], [-34.61, -58.613],
];
const NO_VISTA = [[-31.32, -64.21], [-32.89, -68.83]];

function prng(semilla) { // mulberry32: el mismo lote en cada corrida
  let a = semilla >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function lote(semilla) {
  const r = prng(semilla);
  const paso = new Date(Date.UTC(2026, 10, 12, 18, 0, 0));
  const ciclo = new Date(paso.getTime() - 8 * 3600e3).toISOString();
  const filas = [];
  for (let i = 0; i < FILAS; i++) {
    const z = r();
    let lat, lon;
    if (z < 0.6) { const e = ESTACIONES[Math.floor(r() * ESTACIONES.length)]; lat = e[0] + (r() - 0.5) * 0.12; lon = e[1] + (r() - 0.5) * 0.12; }
    else if (z < 0.9) { const e = ESTACIONES[Math.floor(r() * ESTACIONES.length)]; lat = e[0] + (r() - 0.5) * 1.5; lon = e[1] + (r() - 0.5) * 1.5; }
    else { const e = NO_VISTA[Math.floor(r() * NO_VISTA.length)]; lat = e[0] + (r() - 0.5) * 0.5; lon = e[1] + (r() - 0.5) * 0.5; }
    const anticip = r() < 0.05 ? 6.5 + r() * 3 : r() * 6;
    const llueve = r() < 0.15;
    const mm = () => (llueve ? Math.round(r() * 80) / 10 : r() < 0.8 ? 0 : Math.round(r() * 5) / 10);
    const v = r();
    const votos = v < 0.6 ? 0 : v < 0.8 ? 1 : v < 0.92 ? 2 : 3;
    const falta = r() < 0.03 ? ["gfs", "ifs", "wrf"][Math.floor(r() * 3)] : null;
    const lluvia = {}; const ciclos = {};
    for (const m of ["gfs", "ifs", "wrf"]) { lluvia[m] = m === falta ? null : mm(); ciclos[m] = ciclo; }
    filas.push({
      lat: Math.round(lat * 1e4) / 1e4, lon: Math.round(lon * 1e4) / 1e4,
      hora_paso_utc: paso.toISOString(),
      emision_utc: new Date(paso.getTime() - anticip * 3600e3).toISOString(),
      votos, lluvia_mm_3h: lluvia, ciclos,
    });
  }
  return JSON.stringify({ filas });
}

const LOTES = Array.from({ length: VARIANTES }, (_, i) => lote(1000 + i));
const PARAMS = { headers: Object.assign({ "Content-Type": "application/json" }, __ENV.CLAVE ? { "X-API-Key": __ENV.CLAVE } : {}), timeout: "60s" };

export function setup() { // calienta: el primer pedido de cada pod carga cosas y no debe contar
  for (let i = 0; i < 5; i++) http.post(`${URL}/predict`, LOTES[i % VARIANTES], PARAMS);
}

export default function () {
  const res = http.post(`${URL}/predict`, LOTES[(__VU + __ITER) % VARIANTES], PARAMS);
  check(res, { "200 y todos los tramos": (r) => r.status === 200 && r.json("filas").length === FILAS });
}

// Una línea JSON con lo que va a la tabla del informe (la lee lluvia-grilla.sh).
export function handleSummary(d) {
  const m = d.metrics, dur = m.http_req_duration.values, n = m.http_reqs.values.count;
  const seg = d.state.testRunDurationMs / 1000;
  const r2 = (x) => Math.round(x * 100) / 100;
  const linea = {
    resultado_k6: true, filas: FILAS, vus: VUS, duracion_s: r2(seg), pedidos: n,
    pedidos_s: r2(m.http_reqs.values.rate), tramos_s: Math.round(m.http_reqs.values.rate * FILAS),
    ms_prom: r2(dur.avg), ms_p50: r2(dur.med), ms_p90: r2(dur["p(90)"]), ms_p95: r2(dur["p(95)"]),
    ms_p99: r2(dur["p(99)"]), ms_max: r2(dur.max), errores: r2(m.http_req_failed.values.rate * 100),
    checks_ok: r2((m.checks ? m.checks.values.rate : 0) * 100),
  };
  return { stdout: JSON.stringify(linea) + "\n" };
}
