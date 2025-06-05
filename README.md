# NetVision

**NetVision** ist ein Netzwerkdokumentationstool, das ich gemeinsam mit meinem Projektpartner Thomas Hundsbichler entwickelt habe. Es vereinfacht und zentralisiert die Dokumentation von Netzwerkverbindungen in Serverschränken. So können Administratoren schnell nachvollziehen, welches Patchkabel mit welchem Switch verbunden ist – das reduziert Fehler, spart Zeit und sorgt für mehr Übersichtlichkeit im Netzwerkmanagement.

---

## ✨ Funktionen

- **Automatisches Konfigurations-Parsen**  
  Das Backend liest periodisch Konfigurationsdateien von Netzwerkswitches aus, um Informationen zur Netzwerktopologie und zu Verbindungen zu extrahieren.

- **Zentrale Datenbank**  
  Alle Daten werden in einer zentralen MySQL-Datenbank gespeichert. Jeder Switch wird dabei eindeutig durch `hostname` und eine ID identifiziert.

- **Benutzerfreundliches Webinterface**  
  Die Webanwendung ermöglicht eine einfache Verwaltung und Visualisierung der gesammelten Daten.

- **Responsives Design**  
  Die Oberfläche ist für Desktop- und Mobilgeräte optimiert.

---

## 🧱 Projektstruktur

- **Backend**  
  Ein Serverdienst, der zyklisch Konfigurationsdateien von Switches ausliest, verarbeitet und die Daten in der Datenbank ablegt.

- **Frontend**  
  Eine Webanwendung zur Verwaltung und Visualisierung der Netzwerktopologie.

---

## ⚙️ Installationsanleitung – Backend

Folge diesen Schritten, um das NetVision-Backend auf deinem lokalen System einzurichten.

### Voraussetzungen

- Python 3.8 oder höher  
- MySQL Server  
- Git

---

### Schritt 1: Repository klonen

```bash
git clone https://github.com/breburda-dejan/netvision.git
cd netvision
````

---

### Schritt 2: Virtuelle Umgebung erstellen

```bash
python -m venv venv
source venv/bin/activate  # Unter Windows: venv\Scripts\activate
```

---

### Schritt 3: Bibliotheken installieren

```bash
pip install -r requirements.txt
```

---

### Schritt 4: Umgebungsvariablen konfigurieren

Erstelle oder bearbeite die Datei `.env` im Projektverzeichnis:

```env
NETVISION_API_KEY=your_api_key
NETVISION_DB_PASS=your_DB_Password
NETVISION_DB_USER=your_DB_Username
```

Ersetze die Platzhalter mit deinen echten Werten.

---

### Schritt 5: Datenbank initialisieren

Stelle sicher, dass der MySQL-Server läuft. Melde dich an:

```bash
mysql -u your_db_user -p
```

Dann im MySQL-Terminal:

```sql
-- Datenbank erstellen
CREATE DATABASE IF NOT EXISTS NetVisionDB;
USE NetVisionDB;

-- Tabelle "switch" erstellen
CREATE TABLE switch (
    id_Switch INT AUTO_INCREMENT,
    hostname VARCHAR(255) NOT NULL UNIQUE,
    modell VARCHAR(255),
    no_fports INT,
    PRIMARY KEY (id_Switch, hostname)
);

-- Tabelle "port" erstellen
CREATE TABLE port (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_Switch INT NOT NULL,
    hostname VARCHAR(255) NOT NULL,
    portname VARCHAR(255) NOT NULL,
    description TEXT,
    portmode VARCHAR(512),
    FOREIGN KEY (id_Switch, hostname) REFERENCES switch(id_Switch, hostname)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);
```

---

### Schritt 6: Selbstsigniertes Zertifikat erstellen

Zertifikatsordner erstellen (falls nicht vorhanden):

```bash
mkdir -p Cert
```

Privaten Schlüssel erstellen:

```bash
openssl genrsa -out Cert/key.pem 2048
```

Zertifikat generieren:

```bash
openssl req -new -x509 -key Cert/key.pem -out Cert/cert.pem -days 365
```

> Folge den Anweisungen in der Konsole. Du kannst die Gültigkeit mit `-days` anpassen.

---

### Schritt 7: Einstellungen anpassen (optional)

Je nach Umgebung und Anwendungsfall können Konfigurationswerte angepasst werden.

---

### Schritt 8: Konfigurationsdateien hinzufügen

Lege deine Switch-Konfigurationsdateien im Ordner `/Config-files` ab.

---

### Schritt 9: Server starten

```bash
python DA_Server.py
```

---

## 📬 Feedback

Fehler, Feature-Requests oder Verbesserungen?
Erstelle ein [Issue](https://github.com/breburda-dejan/netvision/issues) oder sende einen Pull Request.
