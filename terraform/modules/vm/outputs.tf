output "instance_name" {
  value = google_compute_instance.this.name
}

output "external_ip" {
  value = google_compute_instance.this.network_interface[0].access_config[0].nat_ip
}

output "data_disk_name" {
  value = google_compute_disk.data.name
}
