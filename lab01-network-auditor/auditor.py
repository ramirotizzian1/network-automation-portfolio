#!/usr/bin/env python3
"""
Lab 01 - Network Auditor
Conecta a routers MikroTik via SSH usando Netmiko,
recolecta información de interfaces y genera reporte CSV + JSON.
"""

import yaml
import json
import csv
import os
from datetime import datetime
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, AuthenticationException

# ── Si instalaste 'rich', descomentar estas líneas para output bonito
# from rich.console import Console
# from rich.table import Table
# console = Console()


def load_inventory(path: str) -> list:
    """Carga el inventario desde un archivo YAML."""
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data["devices"]


def audit_device(device: dict) -> dict:
    """
    Se conecta a un dispositivo y recolecta:
    - Identidad / hostname
    - Versión de RouterOS
    - Interfaces (nombre, IP, estado)
    - Recursos del sistema (CPU, RAM)
    """
    result = {
        "name": device["name"],
        "hostname": device["hostname"],
        "status": "unreachable",
        "routeros_version": None,
        "interfaces": [],
        "cpu_load": None,
        "free_memory_mb": None,
        "timestamp": datetime.now().isoformat(),
    }

    connection_params = {
        "device_type": device["device_type"],
        "host": device["hostname"],
        "port": device.get("port", 22),
        "username": device["username"],
        "password": device["password"],
    }

    try:
        print(f"[+] Conectando a {device['name']} ({device['hostname']})...")
        net_connect = ConnectHandler(**connection_params)

        result["status"] = "reachable"

        # ── Versión de RouterOS
        version_output = net_connect.send_command(
            "/system resource print", use_textfsm=False
        )
        for line in version_output.splitlines():
            if "version:" in line.lower():
                result["routeros_version"] = line.split(":")[1].strip()
                break

        # ── CPU y memoria
        for line in version_output.splitlines():
            if "cpu-load:" in line.lower():
                result["cpu_load"] = line.split(":")[1].strip()
            if "free-memory:" in line.lower():
                result["free_memory_mb"] = line.split(":")[1].strip()

        # ── Interfaces con sus IPs
        iface_output = net_connect.send_command(
            "/ip address print detail", use_textfsm=False
        )

        # Parseo simple línea por línea
        current_iface = {}
        for line in iface_output.splitlines():
            line = line.strip()
            if "address=" in line:
                # Extraer campos clave
                iface_data = {}
                for token in line.split():
                    if "=" in token:
                        key, _, value = token.partition("=")
                        iface_data[key] = value
                if iface_data:
                    result["interfaces"].append({
                        "interface": iface_data.get("interface", "N/A"),
                        "address": iface_data.get("address", "N/A"),
                        "network": iface_data.get("network", "N/A"),
                        "disabled": iface_data.get("disabled", "false"),
                    })

        net_connect.disconnect()
        print(f"    ✓ {device['name']} auditado correctamente")

    except AuthenticationException:
        result["status"] = "auth_failed"
        print(f"    ✗ {device['name']}: fallo de autenticación")

    except NetmikoTimeoutException:
        result["status"] = "timeout"
        print(f"    ✗ {device['name']}: timeout de conexión")

    except Exception as e:
        result["status"] = f"error: {str(e)}"
        print(f"    ✗ {device['name']}: error inesperado — {e}")

    return result


def save_reports(results: list, output_dir: str):
    """Guarda los resultados en formato JSON y CSV."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── JSON (datos completos)
    json_path = os.path.join(output_dir, f"audit_{timestamp}.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[✓] Reporte JSON guardado: {json_path}")

    # ── CSV (vista plana por interfaz)
    csv_path = os.path.join(output_dir, f"audit_{timestamp}.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "device_name", "hostname", "status",
            "routeros_version", "cpu_load", "free_memory_mb",
            "interface", "address", "network", "disabled", "timestamp"
        ])
        for device in results:
            if device["interfaces"]:
                for iface in device["interfaces"]:
                    writer.writerow([
                        device["name"], device["hostname"], device["status"],
                        device["routeros_version"], device["cpu_load"],
                        device["free_memory_mb"], iface["interface"],
                        iface["address"], iface["network"], iface["disabled"],
                        device["timestamp"]
                    ])
            else:
                # Dispositivo sin interfaces o inalcanzable
                writer.writerow([
                    device["name"], device["hostname"], device["status"],
                    device["routeros_version"], device["cpu_load"],
                    device["free_memory_mb"], "-", "-", "-", "-",
                    device["timestamp"]
                ])
    print(f"[✓] Reporte CSV guardado: {csv_path}")


def print_summary(results: list):
    """Imprime un resumen en consola."""
    print("\n" + "="*50)
    print("         RESUMEN DE AUDITORÍA")
    print("="*50)
    for d in results:
        print(f"\n  Dispositivo : {d['name']} ({d['hostname']})")
        print(f"  Estado      : {d['status']}")
        print(f"  RouterOS    : {d['routeros_version']}")
        print(f"  CPU Load    : {d['cpu_load']}")
        print(f"  Free Memory : {d['free_memory_mb']}")
        print(f"  Interfaces  : {len(d['interfaces'])} encontradas")
        for iface in d["interfaces"]:
            print(f"    ↳ {iface['interface']:12} {iface['address']:20} disabled={iface['disabled']}")
    print("="*50)


def main():
    inventory = load_inventory("inventory.yaml")
    print(f"\n[*] Iniciando auditoría de {len(inventory)} dispositivos...\n")

    results = []
    for device in inventory:
        result = audit_device(device)
        results.append(result)

    print_summary(results)
    save_reports(results, "reports")


if __name__ == "__main__":
    main()
