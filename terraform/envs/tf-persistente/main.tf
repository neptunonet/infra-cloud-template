# Trabajo Final: lo que PERSISTE del servicio de lluvia, separado de lo que se prende y se apaga.
#
# Lección de la cursada (Clase 5, error 409): un destroy de envs/dev se llevó el registry y su state quedó
# desfasado. Acá va solo lo que no se tiene que perder nunca: el bucket de datos y modelos y las identidades
# que lo usan. El clúster (envs/dev) se puede destruir todas las veces que haga falta sin tocar esto.
#
#   gs://<proyecto>-lluvia/
#     datasets/AAAA-MM-DD.parquet   lo sube el VPS de Clima Rutero (export diario)
#     modelos/activa.json           puntero a la versión activa (lo mueve train.py)
#     modelos/versiones/vAAAAMMDD_HHMMSS/{modelo.joblib,metadata.json}

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  bucket = "${var.project_id}-lluvia"
}

resource "google_storage_bucket" "lluvia" {
  name                        = local.bucket
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # Versionado: si algo pisa activa.json o un dataset, la versión anterior queda.
  versioning {
    enabled = true
  }

  # Las versiones viejas no se guardan para siempre: se borran a los 30 días.
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
      with_state                 = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    proyecto = "trabajo-final"
    servicio = "lluvia"
  }

  # Un `tofu destroy` de este entorno falla en vez de borrar datos y modelos.
  lifecycle {
    prevent_destroy = true
  }
}

# ---------- VPS de Clima Rutero: solo puede CREAR objetos en datasets/ (decisión 18) ----------
# No lee, no borra, no pisa y no ve modelos/. El VPS no está en GCP, así que usa una clave de esta cuenta;
# la clave NO se crea acá (quedaría en el state): se crea con gcloud y vive solo en el VPS.
resource "google_service_account" "export" {
  account_id   = "lluvia-export"
  display_name = "lluvia: export diario desde el VPS (solo crea en datasets/)"
}

resource "google_storage_bucket_iam_member" "export_crea_datasets" {
  bucket = google_storage_bucket.lluvia.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.export.email}"

  condition {
    title       = "solo-datasets"
    description = "Solo objetos bajo datasets/"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${local.bucket}/objects/datasets/\")"
  }
}

# El export corre en el VPS con la imagen multi-arch de lluvia (exportar.py): esta cuenta tiene que poder bajarla.
# Solo lectura y solo sobre el repositorio del curso.
resource "google_artifact_registry_repository_iam_member" "export_baja_imagen" {
  location   = var.region
  repository = var.ar_repository
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.export.email}"
}

# ---------- Pods de GKE (API y Job de entrenamiento) ----------
# Leen todo el bucket y escriben solo en modelos/. Se conectan por Workload Identity (sin claves) cuando se
# prende el clúster; ese vínculo va en envs/dev.
resource "google_service_account" "servicio" {
  account_id   = "lluvia-servicio"
  display_name = "lluvia: API y entrenamiento en GKE (lee datos, escribe modelos/)"
}

resource "google_storage_bucket_iam_member" "servicio_lee" {
  bucket = google_storage_bucket.lluvia.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.servicio.email}"
}

resource "google_storage_bucket_iam_member" "servicio_escribe_modelos" {
  bucket = google_storage_bucket.lluvia.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.servicio.email}"

  condition {
    title       = "solo-modelos"
    description = "Crear, pisar y borrar solo bajo modelos/ (activa.json y versiones)"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${local.bucket}/objects/modelos/\")"
  }
}

# ---------- Entrenamiento diario en el VPS (decisión 30) ----------
# Mismos permisos sobre el bucket que los pods (lee todo, escribe solo en modelos/) más bajar la imagen. Es una
# cuenta aparte para que la de los pods siga sin ninguna clave: esta sí tiene una, que vive solo en el VPS.
resource "google_service_account" "entrena" {
  account_id   = "lluvia-entrena"
  display_name = "lluvia: entrenamiento diario en el VPS (lee datos, escribe modelos/)"
}

resource "google_storage_bucket_iam_member" "entrena_lee" {
  bucket = google_storage_bucket.lluvia.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.entrena.email}"
}

resource "google_storage_bucket_iam_member" "entrena_escribe_modelos" {
  bucket = google_storage_bucket.lluvia.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.entrena.email}"

  condition {
    title       = "solo-modelos"
    description = "Crear, pisar y borrar solo bajo modelos/ (activa.json y versiones)"
    expression  = "resource.name.startsWith(\"projects/_/buckets/${local.bucket}/objects/modelos/\")"
  }
}

resource "google_artifact_registry_repository_iam_member" "entrena_baja_imagen" {
  location   = var.region
  repository = var.ar_repository
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.entrena.email}"
}
