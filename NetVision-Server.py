"""
ooooo      ooo               .   oooooo     oooo  o8o            o8o
`888b.     `8'             .o8    `888.     .8'   `"'            `"'
 8 `88b.    8   .ooooo.  .o888oo   `888.   .8'   oooo   .oooo.o oooo   .ooooo.  ooo. .oo.
 8   `88b.  8  d88' `88b   888      `888. .8'    `888  d88(  "8 `888  d88' `88b `888P"Y88b
 8     `88b.8  888ooo888   888       `888.8'      888  `"Y88b.   888  888   888  888   888
 8       `888  888    .o   888 .      `888'       888  o.  )88b  888  888   888  888   888
o8o        `8  `Y8bod8P'   "888"       `8'       o888o 8""888P' o888o `Y8bod8P' o888o o888o

============================================================================================
File:           NetVision-Server.py
Description:    This Program periodically reads Switch-Configuration-files and stores relevant information into a Database.
Author:         Breburda Dejan
Version:        1.0

License:        MIT License
                https://opensource.org/licenses/MIT

Github:         https://github.com/Breburda-Dejan/NetVision
Contact:        dejan@breburda.at
============================================================================================
"""
import datetime
import os
import socket
from functools import wraps
from pathlib import Path
import re
from dotenv import load_dotenv
import mysql.connector
from time import time,sleep
import json
from flask import Flask, request, jsonify
import threading
import paramiko

api_key = None
db_password = None
db_username = None
db_connection = None
db_cursor = None

logsenabled = True

COLORS = {
    'reset': '\033[0m',
    'high': '\033[31m',
    'low': '\033[32m',
    'medium': '\033[33m'
}

Settings = {}

SearchCriteria = {}

logs = []


def wait_until_programm_end():
    global cycle_end_tag
    log("Waiting for Cycle to end...","medium",2)
    enablelogs(0)
    while not cycle_end_tag:
        sleep(0.1)
        print(".",end="")
    enablelogs(1)
    print()
    log("Cycle Ended!","medium",2)
    return


def tftp_download(server_ip, remote_file, local_file) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
    rrq = b'\x00\x01' + remote_file.encode('ascii') + b'\x00' + b'octet' + b'\x00'
    server_addr = (server_ip, 69)
    try:
        sock.sendto(rrq, server_addr)

        with open(local_file, 'wb') as f:
            while True:
                data, addr = sock.recvfrom(516)
                opcode = data[0:2]
                block_num = data[2:4]
                if opcode == b'\x00\x03':
                    f.write(data[4:])
                    ack = b'\x00\x04' + block_num
                    sock.sendto(ack, addr)
                    if len(data) < 516:
                        break
                else:
                    raise Exception("Unexpected TFTP response")

    except Exception as e:
        log(f"Error downloading {remote_file}: {e}","high",2)
    finally:
        sock.close()


def connect_to_switch_with_ssh(switch_ip:str,switch_user:str,switch_password:str):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            switch_ip,
            username=switch_user,
            password=switch_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=5
        )
        log(f"Connected to Switch {switch_ip}","low",2)
    except Exception as e:
        log(f"Error: {e}","high",3)
        return None
    return client


def copy_running_config_to_tftp(client:paramiko.client,switch_enable_password:str,tftp_server:str,config_file:str)->None:
    shell = client.invoke_shell()
    shell.send("enable\n")
    sleep(1)
    shell.send(switch_enable_password + "\n")
    sleep(1)
    shell.send(f"copy running-config tftp://{tftp_server}/{config_file}\n")
    shell.recv(1024)
    shell.send("\n")
    shell.recv(1024)
    shell.send("\n")
    sleep(5)
    shell.close()
    client.close()


def live_download(hostname:str, filename:str) -> bool:
    try:
        switch_live_settings = Settings["switch-live-access"][hostname.upper()]
        tftp_server:str = Settings["tftp-settings"]["ip-address"]
        switch_ip:str = switch_live_settings["ip-address"]
        switch_user:str = switch_live_settings["username"]
        switch_password:str = switch_live_settings["password"]
        switch_enable_password:str = switch_live_settings["enable-password"]
        config_file:str = Settings["tftp-settings"]["config-files-path"]+filename
        filepath:str = Settings["Config-Files-Path"] + "/" + filename


        client = connect_to_switch_with_ssh(switch_ip=switch_ip,switch_user=switch_user,switch_password=switch_password)
        if client is None:
            raise Exception("ERROR: client not connected")

        copy_running_config_to_tftp(client,switch_enable_password,tftp_server,config_file)

        log(f"Copied running-config from {hostname}[{switch_ip}] to tftp-server[{tftp_server}]","low",2)

        tftp_download(tftp_server,config_file,filepath)

        log(f"Downloaded running-config from tftp-server[{tftp_server}] to {config_file}","low",2)
        return True
    except Exception as e:
        log(str(e), "high", 3)
        log(f"Error: Unable to connect to {hostname}","medium",2)

        return False


def save_settings() -> None:
    try:
        log("Saving Settings...","low",2)
        settings_to_save = Settings.copy()
        as_temp = {}
        del settings_to_save["as-keys"]
        for key,_ in Settings.items():
            if key in Settings['as-keys'].keys():
                if Settings['as-keys'][key] not in as_temp.keys():
                    as_temp[Settings['as-keys'][key]] = {}
                as_temp[Settings['as-keys'][key]][key] = settings_to_save[key]
                del settings_to_save[key]
        settings_json = json.dumps(settings_to_save, indent=4)
        as_json = {}
        for file in as_temp.keys():
            as_json[file] = json.dumps(as_temp[file], indent=4)
            with open(file, 'w') as outfile:
                log(f"Saving settings to {file}", "low", 3)
                outfile.write(as_json[file])

        with open("settings.json",'w') as outfile:
            log("Saving settings to settings.json", "low", 3)
            outfile.write(settings_json)
    except Exception as e:
        log("ERROR while saving Settings", "high",1)
        #error_exit()       // not needed


def load_settings() -> None:
    try:
        global Settings
        log("Loading settings...", "low", 0)
        if not Path("settings.json").is_file():
            log("No Settings File found, using default settings","medium",0)
            return

        file_content: str = get_content("settings.json")
        Settings = json.loads(file_content)
        log(f"Inserting Settings in local variable", "low", 2)
        try:
            log("Loading extra Settings...","low",0)
            Settings['as-keys'] = {}
            for setting_file in Settings["Additional-Settings-Files"]:
                additional_settings:dict = json.loads(get_content(Settings["Additional-Settings-Files"][setting_file]["location-of-file"]))
                for key,value in additional_settings.items():
                    Settings['as-keys'][key] = Settings["Additional-Settings-Files"][setting_file]["location-of-file"]
                    Settings[key] = value
        except Exception as e:
            log("ERROR loading extra settings","high",0)
        load_env_values()
    except:
        log("ERROR while loading settings", "high",0)


def auto_fix(what_to_fix:str) -> bool:
    try:
        if what_to_fix == '':
            return False
        log(f"Trying to fix {what_to_fix}", "medium",0)
        if what_to_fix == 'folder':
            config_files_folder = Settings["Config-Files-Path"]
            config_files_blueprints = Settings["Config-Files-Blueprints"]
            log_files_folder = Settings["logging-location"]

            if config_files_folder == "" or config_files_blueprints == "" or log_files_folder == "":
                log("ERROR: Path to at least one folder was not provided", "high",1)
            else:
                try:
                    if not Path(config_files_folder).is_dir():
                        os.makedirs(Path(config_files_folder))
                    if not Path(config_files_blueprints).is_dir():
                        os.mkdir(Path(config_files_blueprints))
                    if not Path(log_files_folder).is_dir():
                        os.mkdir(Path(log_files_folder))
                    log("The Program was able to fix the folder structure!", "medium",1)
                    return True
                except:
                    log("ERROR: Could not create folders", "high",1)
                    return False

        elif what_to_fix == 'logging-level':
            try:
                if Settings["logging-level"].isdigit():
                    if not int(Settings["logging-level"]) in [1,2,3]:
                        raise Exception
                    log(f"Setting logging-level to level {Settings['logging-level']}", "medium", 0)
                    Settings["logging-level"] = int(Settings["logging-level"])
                else:
                    raise Exception
            except:
                log("Setting logging-level to level 2 (Basic)", "medium", 0)
                Settings["logging-level"] = 2
            return True

        elif what_to_fix == 'cycle-time':
            log("Setting cycle-time to 7 days","medium",0)
            Settings["cycle-time"] = "7D"
            return True

        elif what_to_fix == 'port-id-reset':
            try:
                log("parsing \"Full-Port-Id-RESET\" to an boolean ", "low", 3)
                Settings["db-settings"]["Full-Port-Id-RESET"] = strtobool(Settings["db-settings"]["Full-Port-Id-RESET"])
                if not Settings["db-settings"]["Full-Port-Id-RESET"] in [True, False]:
                    raise Exception
            except:
                log("ERROR in Settings: \"Full-Port-Id-RESET\" is not a boolean", "high", 1)
                log("Setting Full-Port-Id-RESET to False", "medium", 1)
                Settings["db-settings"]["Full-Port-Id-RESET"] = False
            return True

        elif what_to_fix == 'write-logs-to-file':
            try:
                log("parsing \"write-logs-to-file\" to an boolean ", "low", 3)
                Settings["write-logs-to-file"] = strtobool(Settings["write-logs-to-file"])
                if not Settings["write-logs-to-file"] in [True, False]:
                    raise Exception
            except:
                log("ERROR in Settings: \"write-logs-to-file\" is not a boolean", "high", 1)
                log("Setting write-logs-to-file to False", "medium", 1)
                Settings["write-logs-to-file"] = False
            return True



    except:
        log("ERROR in AUTO-FIX", "high",1)
        error_exit()
        return False


def load_env_values() -> None:
    global db_username,db_password,api_key
    try:
        log("Loading environment variables", "low",2)
        p = os.getenv(Settings["db-settings"]["Database-credentials"]["password"])
        u = os.getenv(Settings["db-settings"]["Database-credentials"]["username"])
        a = os.getenv(Settings["API-KEY"])
        if p: db_password = p
        if u: db_username = u
        if a: api_key = a

    except:
        log("ERROR loading environment variables", "high",1)


def strtobool(string:str) -> bool:
    if string.lower() in ('yes', 'true', 't', 'y', 'ja', 'j', '1'):
        return True
    else:
        return False


def load_switch_model_blueprints() -> None:
    try:
        log("Loading switch model blueprints...", "low", 1)
        try:
            files: list[str] = os.listdir(Settings["Config-Files-Blueprints"])
            log(f"Got {len(files)} files","low",3)
        except:
            log(f"ERROR: can't get files from \"{Settings['Config-Files-Blueprints']}\"","high",1)
            error_exit()

        for file in files:
            file_content:str = get_content(Settings["Config-Files-Blueprints"]+"/"+file)
            modell:str = file.split(".")[0]
            SearchCriteria[modell] = json.loads(file_content)
            log(f"Inserting Blueprint for {modell} into SearchCriteria...","low",2)
    except:
        log("ERROR while loading switch model blueprints", "high",1)


def connect_to_databse() -> bool:        # Mit Datenbank verbinden
    global db_connection,db_cursor
    log("Connecting to Database...", "low", 2)
    try:
        db_connection = mysql.connector.connect(
            host=Settings["db-settings"]["Database-URL"],
            user=db_username,
            password=db_password,
            database=Settings["db-settings"]["Database-Name"]
        )
        db_cursor = db_connection.cursor()
        return True
    except:
        log("Could not connect to MySQL-Database", "high", 1)
        return False


def close_db_connection() -> None:
    global db_connection,db_cursor
    log("Closing Database Connection...","low",2)
    try:
        db_cursor.close()
        db_connection.close()
    except:
        log("Could not close Database Connection","medium",2)


def delete_ports_from_switch(switchid) -> bool:
    try:
        delete_ports_sql = f"DELETE FROM {Settings["db-settings"]["Tables"]["Port"]["table-name"]} WHERE {Settings["db-settings"]["Tables"]["Port"]["switch-id"]} = %s"
        delete_ports_sql_values = (str(switchid),)
        db_cursor.execute( delete_ports_sql, delete_ports_sql_values)
        db_connection.commit()
        return True
    except Exception as e:
        log(f"ERROR deleteing ports from switch {switchid}\n\tError: {e}","high",1)
        return False


def insert_switch(name:str,model:str = None,number_of_ports:str = None) -> bool:
    try:
        log(f"Insert Switch {name}","low",3)
        table_name = Settings["db-settings"]["Tables"]["Switch"]["table-name"]
        switch_name = Settings["db-settings"]["Tables"]["Switch"]["switch-name"]
        switch_model = Settings["db-settings"]["Tables"]["Switch"]["switch-model"]
        switch_port_number = Settings["db-settings"]["Tables"]["Switch"]["switch-port-number"]
        sql = f"INSERT INTO {table_name} ({switch_name}, {switch_model}, {switch_port_number}) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE {switch_model} = VALUES({switch_model}), {switch_port_number} = VALUES({switch_port_number})"
        werte = (name, model, number_of_ports)

        db_cursor.execute(sql, werte)
        db_connection.commit()
        return True
    except Exception as e:
        log(f"ERROR inserting switch {name}\n\tError: {e}", "high", 1)
        return False      #bad request


def Port_Critical_ID_reset() -> None:
    global run
    try:
        log("RESETING Port-ID's function started.","low",1)
        if not connect_to_databse():
            log("Can't RESET Port-ID's without DB-Connection","high",1)
            return
        log("Full RESET of Port-ID's in 10 seconds","high",1)
        sleep(10)
        if run:
            port_table_name = Settings["db-settings"]["Tables"]["Port"]["table-name"]
            log("Resetting","high",1)
            reset_sql = f"DELETE FROM {port_table_name}; ALTER TABLE {port_table_name} AUTO_INCREMENT = 1;"
            db_cursor.execute(reset_sql)
            log("Full RESET Done!","medium",1)
            Settings["db-settings"]["Full-Port-Id-RESET"] = 0
            save_settings()
            close_db_connection()
    except:
        log("ERROR while resetting Port-ids", "high",1)


def insert_port(switchid:int,name:str,description:str = None,portmode:str = None) -> bool:
    try:
        port_table_name = Settings["db-settings"]["Tables"]["Port"]["table-name"]
        port_switch_id = Settings["db-settings"]["Tables"]["Port"]["switch-id"]
        port_name = Settings["db-settings"]["Tables"]["Port"]["port-name"]
        port_description= Settings["db-settings"]["Tables"]["Port"]["port-description"]
        port_switchport = Settings["db-settings"]["Tables"]["Port"]["port-switchport"]
        insert_ports_sql = f"INSERT INTO {port_table_name} ({port_name}, {port_description}, {port_switchport}, {port_switch_id}) VALUES (%s, %s, %s, %s)"
        insert_ports_sql_values = (name, description, portmode, switchid)

        db_cursor.execute(insert_ports_sql, insert_ports_sql_values)
        db_connection.commit()
        lastid = db_cursor.lastrowid
        if lastid >= 2_147_480_000:
            log("Warning: ID is reaching critical high Value! putting Full RESET in Program que ","medium",1)
            Settings["Full-Port-Id-RESET"] = True
    except Exception as e:
        log(f"ERROR inserting port {name}", "high", 1)
        return False      #bad request


def insert_into_DB(data:dict[str:dict[str:str], str:dict[str:str]]) -> None:
    global run
    try:
        # get basic variables #
        switchname = data["Geraeteinformationen"]["Name"]
        model = data["Geraeteinformationen"]["Manufacture"]
        nofports = data["Geraeteinformationen"]["NumberOfPorts"]

        switch_id = Settings["db-settings"]["Tables"]["Switch"]["switch-id"]
        switch_table = Settings["db-settings"]["Tables"]["Switch"]["table-name"]
        switch_name = Settings["db-settings"]["Tables"]["Switch"]["switch-name"]
        #######################

        response_from_insert_Switch = insert_switch(switchname,model,nofports)
        
        if response_from_insert_Switch:                                             # Checking for errors
            switchid = db_cursor.lastrowid                        # Getting insertet switch id
            if switchid == 0:                                                       #if no id, get the id from switchname
                sql_select = f"SELECT {switch_id} FROM {switch_table} WHERE {switch_name} = %s"
                values = (str(switchname),)
                db_cursor.execute(sql_select, values)
                switchid = db_cursor.fetchone()[0]
            log(f"Deleting old Ports from switch {switchname}", "low", 2)
            response_dPorts = delete_ports_from_switch(switchid)
            if response_dPorts:                                          # Checking for errors
                for port in data["Interface"]:
                    if not run:
                        log("Insert into DB interruppted!","medium",1)
                        break
                    description = data["Interface"][port]["Description"]
                    portmode = data["Interface"][port]["Switchport"]
                    insert_port(switchid,port,description,portmode)

    except:
        log(f"ERROR inserting into the database", "high", 1)


def get_files() -> list[str]:
    log("Getting list of config-files","low",2)
    try:
        elements_in_dir: list[str] = os.listdir(Settings["Config-Files-Path"])
        files: list[str] = []
        for element in elements_in_dir:
            if Path(str(Path(Settings["Config-Files-Path"]))+"/"+element).is_file():
                files.append(element)
        log(f"Got {len(files)} files","low",2)
        return files
    except:
        log(f"Error, can't get files from \"{Settings['Config-Files-Path']}\"","high",1)
        error_exit()


def get_content(filepath: str) -> str:
    log(f"Getting content of: {filepath}","low",1)
    try:
        with open(filepath, "r") as file:
            return file.read()
    except:
        log(f"Error reading content from file: {filepath}","high",0)


def identify_device(content: str) -> str:
    try:
        log("Getting device-manufacture","low",1)
        manufacture: str = ""
        for manufacturetocheck in SearchCriteria:
            log(f"Checking if manufacture is: {manufacturetocheck}","low",3)
            if manufacture == "":
                interface_searchCriteria_list: list[str] = SearchCriteria[manufacturetocheck]["check"].values()
                manufacture = manufacturetocheck
                for element in interface_searchCriteria_list:
                    if element not in content:
                        manufacture = ""
                        break

                structureelementindex:int = 0
                lineindex:int = 0
                structureelements:list[str] = list(SearchCriteria[manufacturetocheck]["structure"].values())
                for structureelement in structureelements:
                    i=0
                    for line in content.splitlines():
                        i+=1
                        if structureelements[structureelementindex] in line:
                            if lineindex < i:
                                lineindex = i
                                structureelementindex += 1
                                break
                            else:
                                manufacture = ""
                                break


        if manufacture != "":
            log(f"Device-manufacture: {manufacture}","low",2)
        else:
            log("Cant find device-manufacture, skiping this file","high",1)
        return manufacture
    except:
        log("ERROR while identifying device", "high",1)
        return ""


def extract_information(filepath: str) -> dict[str:dict[str:str], str:dict[str:str]]:
    log(f"Start extracting data from \"{filepath}\"", "low",1)
    extracted_data: dict[str:dict[str:str], str:dict[str:str]] = {
        "Geraeteinformationen": {},
        "Interface": {},
        "VLAN": {}
    }

    content: str = get_content(filepath)
    manufacture: str = identify_device(content)
    name: str = ""

    if manufacture == "":
        return None

    blocks: list[str] = content.split(SearchCriteria[manufacture]["block"])
    for i,block in enumerate(blocks):
        log(f"Checking block {i}","low",3)
        # get Name
        if block.__contains__(SearchCriteria[manufacture]["prefix"]["device"]["name"]):
            for line in block.splitlines():
                if line.__contains__(SearchCriteria[manufacture]["prefix"]["device"]["name"]):
                    name = line.strip().replace(SearchCriteria[manufacture]["prefix"]["device"]["name"], "")
                    log(f"Found device-name: {name}", "low",2)

        # get interface + description + switchport
        if block.strip().startswith(SearchCriteria[manufacture]["prefix"]["interface"]["block"]) and block.__contains__(SearchCriteria[manufacture]["prefix"]["interface"]["relevant"]):
            log(f"Block {i} is an interface-block!","low",3)
            interface: str = ""
            entrys: list[str] = []
            if SearchCriteria[manufacture]["prefix"]["interface"]["entrydisc"] != "":
                entrys = block.split(SearchCriteria[manufacture]["prefix"]["interface"]["entrydisc"])
            else:
                entrys.append(block)

            for entry in entrys:
                try:
                    log("Getting arguments from Interface-entry","low",3)
                    args: dict[str:str] = {}
                    for arg in entry.strip().split(SearchCriteria[manufacture]["prefix"]["interface"]["arg-discriminator"]):
                        try:
                            if not arg.strip().split(SearchCriteria[manufacture]["prefix"]["interface"]["arg-value-discriminator"])[0] in args:
                                args[arg.strip().split(SearchCriteria[manufacture]["prefix"]["interface"]["arg-value-discriminator"])[0]] = ""
                            args[arg.strip().split(SearchCriteria[manufacture]["prefix"]["interface"]["arg-value-discriminator"])[0]] += " ".join(arg.strip().split(SearchCriteria[manufacture]["prefix"]["interface"]["arg-value-discriminator"])[1:]) + "\n"
                        except:
                            pass

                    interface_prefix_id = SearchCriteria[manufacture]["prefix"]["interface"]["id"]

                    if interface_prefix_id.__contains__("##or##"):
                        if interface_prefix_id.split("##or##")[0] in args:
                            interface = args[interface_prefix_id.split("##or##")[0]]
                        else:
                            interface = args[interface_prefix_id.split("##or##")[1]]
                    else:
                        interface = args[interface_prefix_id].strip()

                    try:
                        log(f"Getting description of Interface: {interface}","low",3)
                        description: str = args[SearchCriteria[manufacture]["prefix"]["interface"]["description"]].strip()
                        args.pop(SearchCriteria[manufacture]["prefix"]["interface"]["description"])
                    except:
                        log(f"No description for this Interface: {interface}", "medium",3)
                        description: str = ""
                    try:
                        log(f"Getting Switch-port-information of Interface: {interface}","low",3)
                        if not SearchCriteria[manufacture]["prefix"]["switchport"]["switchport"] == "":
                            switchport: str = args[SearchCriteria[manufacture]["prefix"]["switchport"]["switchport"]].strip()
                            args.pop(SearchCriteria[manufacture]["prefix"]["switchport"]["switchport"])
                        else:
                            switchport:str = interface
                    except:
                        log(f"No Switch-port-information for this Interface: {interface}", "medium",3)
                        switchport: str = ""
                    try:
                        log(f"Getting Extra-information of Interface: {interface}","low",3)
                        extra_information = ""
                        for arg in args:
                            extra_information += f"{arg} {args[arg]}; "
                    except:
                        log(f"No Extra-information for this Interface: {interface}", "medium",3)
                        extra_information: str = ""

                    extracted_data["Interface"][interface] = {}
                    extracted_data["Interface"][interface]["Description"] = description
                    extracted_data["Interface"][interface]["Switchport"] = switchport
                    extracted_data["Interface"][interface]["Extra-information"] = extra_information
                except:
                    pass

    # get geräteinformationen
    extracted_data["Geraeteinformationen"]["Manufacture"] = manufacture
    extracted_data["Geraeteinformationen"]["Name"] = name
    extracted_data["Geraeteinformationen"]["NumberOfPorts"] = len(extracted_data["Interface"])

    log(f"Done extracting data from \"{filepath}\"","low",2)

    return extracted_data


def is_valid_time_string(string:str) -> bool:
    try:
        pattern = r"(\d+[JMDdhms])"
        matches = re.findall(pattern, string)
        valid_string = ''.join(matches)
        if valid_string != string:
            return False
        units = [match[-1] for match in matches]
        return len(units) == len(set(units))
    except:
        log("ERROR while checking time format","high",1)
        return False


def wait_time(time: str) -> int:
    try:
        timeargs:list[str] = time.strip().split(" ")
        time_to_wait: int = 0
        log(f"Specified wait-time: \'{time}\'","low", 3)
        if time == "":
            log("No time specified, exiting...","medium",1)
            exit()
        elif is_valid_time_string(''.join(timeargs)):
            log("time-format is valid.\tCalculating time to wait", "low",2)
            for arg in timeargs:
                if arg.__contains__("J"):
                    time_to_wait += (int(arg.replace("J",""))*31_536_000)
                elif arg.__contains__("M"):
                    time_to_wait += (int(arg.replace("M",""))*2_592_000)
                elif arg.__contains__("D"):
                    time_to_wait += (int(arg.replace("D",""))*86_400)
                elif arg.__contains__("h"):
                    time_to_wait += (int(arg.replace("h",""))*3_600)
                elif arg.__contains__("m"):
                    time_to_wait += (int(arg.replace("m",""))*60)
                elif arg.__contains__("s"):
                    time_to_wait += (int(arg.replace("s",""))*1)
        else:
            log("Wrong time-format...\tExample: \"7D 12h\"","high",1)
            error_exit()
        return time_to_wait
    except:
        log("ERROR while calculating waiting time","high",1)
        error_exit()


def enablelogs(enable):
    global logsenabled,Settings
    logsenabled = enable


def log(message:str, priority:str,loglevel:int) -> None:
    global app,logs,logsenabled,Settings
    try:
        if not logsenabled:
            return
        time:str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.")+f"{int(datetime.datetime.now().microsecond / 1000):03d}"
        logs.append({"priority": priority, "message": message, "time": time})
        prefix:str = f"{time}> "
        if loglevel == 0:
            print(COLORS[priority.lower()] + prefix + message + COLORS["reset"])
        elif loglevel <= Settings["logging-level"]:
                print(COLORS[priority.lower()] + prefix + message + COLORS["reset"])
        try:
            if Settings["logging-location"] != "" and Settings["write-logs-to-file"]:              # Schreibe alle logs in ein file falls ein pfad zu einem ordner angeführt ist
                with open(Settings["logging-location"]+"Log - "+datetime.datetime.now().strftime("%Y-%m-%d")+".log", 'a') as file:
                    file.write(f"{time} | {priority.upper()}> {message}\n")
                    file.close()
            #with app.app_context():
                #requests.post(f"http://127.0.0.1:5001/log",json={"content":f"{priority}#5#{loglevel}#5#{message}#5#{time}"},headers={"X-API-Key":"hu4wSab5zpLQW8wRta6KgeUAFVvcY1r6Ror7bpRQrMU"})
        except Exception as e:
            pass
    except:
        print(COLORS["high"] + "Error in logs, trying to fix settings soon" + COLORS["reset"])


def error_exit() -> None:
    log("Exited due to error","high",0)
    exit(1)


def validating_settings() -> bool:
    try:
        errors:int = 0
        if not Settings["logging-level"] in [1,2,3]:
            print(COLORS["high"]+"Setting ERROR: logging-level is not configured or invalid!"+COLORS["reset"])
            errors +=  (1,0)[auto_fix("logging-level")]
        if not is_valid_time_string(''.join(Settings["cycle-time"].strip().split(" "))):
            log("Setting ERROR: cycle-time format is invalid!","high",1)
            errors +=  (1,0)[auto_fix("cycle-time")]
        if Settings["db-settings"]["Database-URL"] == "" or Settings["db-settings"]["Database-Name"] == "":
            log("Setting ERROR: Database-URL or Database-Name is invalid", "high", 1)
            errors += 1

        try:
            db_errors = 0
            for table in Settings["db-settings"]["Tables"]:
                for entry in Settings["db-settings"]["Tables"][table]:
                    value = Settings["db-settings"]["Tables"][table][entry]
                    if value == "":
                        log(f"Setting ERROR: Value for {entry} is empty","high",3)
                        db_errors += 1
        except:
            log("ERROR while validating db-settings","high",1)
            db_errors += 1

        if db_errors > 0:
            errors += db_errors
            log("Setting ERROR: DB-Settings are invalid! Use 'Loglevel 3' to get more detailed logs","high",1)

        config_files_path = Path(Settings["Config-Files-Path"]).resolve()
        logging_location = Path(Settings["logging-location"]).resolve()
        config_files_blueprints = Path(Settings["Config-Files-Blueprints"]).resolve()
        if not config_files_path.is_dir() or not logging_location.is_dir() or not config_files_blueprints.is_dir():
            log("Setting ERROR: Config-Files-Path, Config-Files-Blueprints or logging-location is not configured or invalid",
                "high", 1)
            errors += (1, 0)[auto_fix("folder")]

        try:
            if Settings["db-settings"]["Full-Port-Id-RESET"]:
                pass
        except:
            errors += (1,0)[auto_fix("port-id-reset")]

        try:
            if Settings["write-logs-to-file"]:
                pass
        except:
            errors += (1,0)[auto_fix("write-logs-to-file")]

        if errors > 0:
            return False
        save_settings()
        return True
    except:
        log("ERROR while validating settings", "high", 1)
        return False

# Main Variables
run = False
cycle_end_tag = False
planed_interrupt = False
cycle:int = 0
end_of_cycle:float = 0.0
time_between_cycles:int = 0

def main() -> None:
    global run,end_of_cycle,time_between_cycles,cycle,cycle_end_tag,planed_interrupt
    planed_interrupt = False
    cycle_end_tag = False
    load_settings()
    run = validating_settings()
    log("Start of Program", "low", 1)
    time_between_cycles = 1
    end_of_cycle = time()
    try:
        if Settings["db-settings"]["Full-Port-Id-RESET"]:
            Port_Critical_ID_reset()
    except:
        pass
    while run:
        if time()-end_of_cycle < time_between_cycles:
            continue

        temp_planed_interrupt = planed_interrupt
        load_settings()
        run = validating_settings()
        if not run:
            break

        if connect_to_databse():
            load_switch_model_blueprints()
            log("Successfully connected to Database", "low", 2)
            log(f"Start of cycle {cycle}", "low", 1)
            allfiles: list[str] = get_files()
            for file in allfiles:
                if not run:
                    temp_planed_interrupt = planed_interrupt
                    break

                filepath = Settings["Config-Files-Path"]+"/"+file
                extracted_data = extract_information(filepath)
                if extracted_data is None:
                    continue

                name = extracted_data["Geraeteinformationen"]["Name"].strip()
                if Settings["switch-live-access"]:
                    try:
                        if Settings["switch-live-access"][name.upper()]:
                            log(f"Trying to download running-config from {name}", "low", 2)
                            if live_download(hostname=name, filename=file):
                                log("Re parsing downloaded file!", "medium", 2)
                                extracted_data = extract_information(filepath=filepath)
                    except Exception as e:
                        pass

                log("Inserting into Database","low",1)
                insert_into_DB(extracted_data)
            close_db_connection()

        else:
            log(f"Skip Cycle {cycle}", "high", 1)


        log(f"End of cycle {cycle}", "low", 1)
        save_settings()
        time_between_cycles = wait_time(Settings["cycle-time"])
        cycle += 1
        end_of_cycle = time()
        log(f"Sleeping for {time_between_cycles}s", "medium", 1)

    if not planed_interrupt:
        log("Unexpected end of Program, check logs for ERRORS", "high", 1)
    else:
        log("Program Ended", "high", 1)
    cycle_end_tag = True

## REST API

app = Flask(__name__)
mainThread = threading.Thread(target=main)


def api_key_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != VALID_API_KEY:
            return jsonify({"error": "Unauthorized", "message": "Invalid or missing API key"}), 401
        return f(*args, **kwargs)
    return wrapper


@app.route("/status",methods=["GET"])
@api_key_required
def status():
    global run,cycle,start_of_cycle,time_between_cycles,logs
    log("Sending Status to GUI","low",1)
    statusmessage = {
        "Running":run,
        "Cycle":cycle,
        "Next-Cycle-In":time_between_cycles-(time()-start_of_cycle),
        "Last-5-logs": logs[-6:-1]
    }
    return jsonify(statusmessage),200


@app.route("/restart", methods=["POST"])
@api_key_required
def restartServer():
    global mainThread
    try:
        stopServer()
        wait_until_programm_end()
        sleep(0.5)
        load_dotenv()
        startServer()
        return jsonify({"Response":"Server restarted"}),200
    except Exception as e:
        log(f"ERROR while restarting server: {e}", "high", 0)
        return jsonify({"Error":"Server did not restart"}),409


@app.route("/logs/<number_of_logs_to_get>", methods=["GET"])
@api_key_required
def sendLogs(number_of_logs_to_get):
    global logs
    try:
        number_of_logs_to_get = int(number_of_logs_to_get)
        if number_of_logs_to_get >= len(logs) or number_of_logs_to_get == -1:
            number_of_logs_to_get = len(logs)
        return (jsonify(
            {
                "Logs":logs[-number_of_logs_to_get-1:-1]
             }
        ),200)
    except Exception as e:
        return jsonify({"Error":"Server was not able to send logs"}),409


@app.route("/start",methods=["POST"])
@api_key_required
def startServer():
    global mainThread
    if not mainThread.is_alive():
        log("Starting the main thread", "medium", 1)
        mainThread.start()
        return jsonify({"Response":"Started the Main thread"}),201
    else:
        return jsonify({"Error":"Already Running."}),409

@app.route("/stop",methods=["POST"])
@api_key_required
def stopServer():
    global run,mainThread,planed_interrupt
    if mainThread.is_alive():
        planed_interrupt = True
        run = False
        mainThread = threading.Thread(target=main)
        log("Stopping the main thread","medium",1)
        return jsonify({"Response":"Stopped the Main thread"}),201
    else:
        mainThread = threading.Thread(target=main)
        return jsonify({"Error":"MainThread is not running"}),409



def insertSettings(new_settings:dict,current_settings:dict, key:str,oldkey:str = "")->str:
    log(f"Processing Settings: {new_settings[key]}", "low", 3)
    fail_response = ""
    if key not in current_settings.keys():
        return f"{key} not found in {(oldkey,'Settings')[oldkey.__eq__('')]}"
    if isinstance(new_settings[key],dict):
        log(f"{new_settings[key]} is another dictionary, going 1 key deeper into the settings...", "low", 3)
        for k in new_settings[key]:
            try:
                log(f"Try to Process Key: {k}", "low", 3)
                fail_response += insertSettings(new_settings[key],current_settings[key],k,key)
            except Exception as e:
                log(f"Error while trying to process settings with key: {k}. Error: {e}", "medium", 2)
    elif key in current_settings.keys():
        log(f"{new_settings[key]} is not another dictionary, replacing old settings with new one...", "low", 3)
        current_settings[key] = new_settings[key]
    else:
        log(f"key: {key} not found in {current_settings}\n","medium", 2)
        return f"{key} not found in {(oldkey,'Settings')[oldkey.__eq__('')]}\n"
    return fail_response


@app.route("/settings",methods=["GET","PUT"])
@api_key_required
def settings():
    global Settings
    if request.method == "GET":
        log(f"Sending Settings to GUI","low",1)
        relevantsettings = Settings.copy()
        ## Setting unrelevant settings to empty string ###
        relevantsettings.pop("API-KEY")
        ##################################################
        return jsonify(relevantsettings),200
    if request.method == "PUT":
        old_Settings = Settings.copy()
        new_settings = request.json
        fail_response = ""
        for key in new_settings:
            try:
                if key not in old_Settings.keys():
                    raise Exception
                fail_response+=insertSettings(new_settings,Settings, key)
            except:
                fail_response+=f"Cant insert value into Settings[{key}]\n"
                log(f"Cant insert value into Settings[{key}]","medium",2)

        if validating_settings() and fail_response.__eq__(""):
            log("Settings updated","medium",1)
            return jsonify({"Response":"Updated Settings successfully"}),200
        else:
            log("Settings not updated","medium",1)
            log("Resetting Settings to Old Settings","medium",3)
            Settings = old_Settings
            return jsonify({"Error":fail_response}),400


if __name__ == '__main__':
    load_dotenv()
    load_settings()
    validating_settings()
    mainThread.start()
    if not api_key == None:
        log("Starting API-Service","low",1)
        VALID_API_KEY = api_key
        app.run(host="0.0.0.0",port=5000,ssl_context=(Settings["ssl-certificate"]["cert.pem"], Settings["ssl-certificate"]["key.pem"]))
        #app.run(host="0.0.0.0",prot=5000)
    else:
        log("ERROR, not able to get API-KEY","high",1)










"""
MIT License

Copyright (c) 2025 Breburda Dejan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights  
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell     
copies of the Software, and to permit persons to whom the Software is         
furnished to do so, subject to the following conditions:                      

The above copyright notice and this permission notice shall be included in    
all copies or substantial portions of the Software.                           

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR    
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,      
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE   
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER       
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN    
THE SOFTWARE.

"""
