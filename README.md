# NetVision

**NetVision** is a network documentation tool developed by me and my project partner, Thomas Hundsbichler. It simplifies and centralizes the documentation of network connections in server racks. This allows administrators to quickly identify which patch cable is connected to which switch—reducing errors, saving time, and improving overall clarity in network management.

---

## Table of Contents

* [Installation Guide](#installation-guide)
* [Configuration](#configuration)

---

## Installation Guide

Follow these steps to set up the NetVision backend on your local system.

### Prerequisites

* Python 3.8 or higher
* MySQL Server
* Git

---

### Step 1: Clone the Repository

```bash
git clone https://github.com/breburda-dejan/netvision.git
cd netvision
```

---

### Step 2: Create a Virtual Environment

```bash
python -m venv venv
```

---

### Step 3: Install Dependencies

```bash
venv/bin/pip install -r requirements.txt
```

---

### Step 4: Initialize the Database

Make sure your MySQL server is running. Then log in:

```bash
mysql -u your_db_user -p
```

In the MySQL terminal, execute:

```sql
-- Create database
CREATE DATABASE IF NOT EXISTS NetVisionDB;
USE NetVisionDB;

-- Create "switch" table
CREATE TABLE switch (
    id_Switch INT AUTO_INCREMENT,
    hostname VARCHAR(255) NOT NULL UNIQUE,
    modell VARCHAR(255),
    no_fports INT,
    PRIMARY KEY (id_Switch, hostname)
);

-- Create "port" table
CREATE TABLE port (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_Switch INT NOT NULL,
    portname VARCHAR(255) NOT NULL,
    description TEXT,
    portmode VARCHAR(512),
    FOREIGN KEY (id_Switch) REFERENCES switch(id_Switch)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);
```

---

### Step 5: Generate a Self-Signed Certificate

Create a certificate folder if it doesn’t exist:

```bash
mkdir -p Cert
```

Generate the private key:

```bash
openssl genrsa -out Cert/key.pem 2048
```

Generate the certificate:

```bash
openssl req -new -x509 -key Cert/key.pem -out Cert/cert.pem -days 365
```

> Follow the instructions in the console. You can adjust the validity with `-days`.

---

### Step 6: Configure Environment Variables

Create or edit the `.env` file in the project directory:

```env
NETVISION_API_KEY=your_api_key
NETVISION_DB_PASS=your_DB_Password
NETVISION_DB_USER=your_DB_Username
```

Replace the placeholders with your actual values.

---

### Step 7: Adjust Configuration Settings

Edit settings such as the database URL and the IP address of the TFTP server to match your environment.

---

### Step 8: Add Configuration Files

Place your switch configuration files in the `/Config-files` directory.

---

### Step 9: Start the Server

```bash
venv/bin/python NetVision-Server.py
```

---

## Configuration

* [Logs](#logs)
* [Cycle Time](#cycle-time)
* [Config Files](#config-files)
* [DB Settings](#db-settings)
* [TFTP Settings](#tftp-settings)
* [Certificate Settings](#certificate-settings)
* [Live Access Settings](#live-access-settings)

### Logs

```json
"logging-level": 1
```

* 1 - Minimum
* 2 - Basic
* 3 - Maximum

```json
"write-logs-to-file": 1
```

* 0 - Don't write logs to file
* 1 - Write logs to file

```json
"logging-location": "logs/"
```

* Location where logs are stored (only if *write-logs-to-file* is set to 1)

---

### Cycle Time

```json
"cycle-time": "7D"
```

* `"1Y 2M 3D 4h 5m 6s"` – 1 Year, 2 Months, 3 Days, 4 Hours, 5 Minutes, 6 Seconds until next cycle
* `"1D 2D"` – Invalid input

---

### Config Files

```json
"Config-Files-Path": "Config-files"
```

* Location of configuration files

```json
"Config-Files-Blueprints": "Config-files/config-file-blueprints"
```

* Location of blueprint templates

---

### Additional Settings Files

```json
"Additional-Settings-Files": {
  "db-settings": {
    "location-of-file": "Settings/db-settings.json"
  }
}
```

* The name `"db-settings"` is arbitrary and can be freely chosen.
* `"location-of-file"` specifies the file path containing additional settings.

---

### DB Settings

```json
"db-settings": {
  "Database-Name": "NetVisionDB",
  "Database-URL": "192.168.0.200",
  "Database-credentials": {
    "password": "NETVISION_DB_PASS",
    "username": "NETVISION_DB_USER"
  }
}
```

* `"Database-Name"` → name of the schema to use
* `"Database-URL"` → IP address or URL of the database
* `NETVISION_DB_PASS` and `NETVISION_DB_USER` are **environment variables**, not plain text passwords

```json
"db-settings": {
  "Tables": {
    "Switch": {
      "table-name": "switch",
      "switch-id": "id_Switch",
      "switch-name": "hostname",
      "switch-model": "modell",
      "switch-port-number": "no_fports"
    },
    "Port": {
      "table-name": "port",
      "switch-id": "id_Switch",
      "port-name": "portname",
      "port-description": "description",
      "port-switchport": "portmode"
    }
  }
}
```

* `"Switch"` and `"Port"` refer to the two database tables
* The keys represent the column names in the database

---

### TFTP Settings

```json
"tftp-settings": {
  "ip-address": "192.168.0.201",
  "config-files-path": "configs/"
}
```

* `"ip-address"` → IP of the TFTP server
* `"config-files-path"` → Directory on the TFTP server where config files are stored

---

### Certificate Settings

```json
"ssl-certificate": {
  "cert.pem": "Cert/cert.pem",
  "key.pem": "Cert/key.pem"
}
```

* `"cert.pem"` → Path to the certificate file
* `"key.pem"` → Path to the private key file

---

### Live Access Settings

Live access is currently supported only for Cisco devices.

```json
"switch-live-access": {
  "Example-hostname": {
    "ip-address": "192.168.0.202",
    "username": "admin",
    "password": "admin",
    "enable-password": "12345678"
  }
}
```

* `"Example-hostname"` → Replace with the actual hostname of your switch
* `"ip-address"` → IP address of the switch
* `"username"` / `"password"` → login credentials
* `"enable-password"` → enable secret of the switch
