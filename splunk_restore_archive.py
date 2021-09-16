import os
import time
import shutil
import subprocess
import sys
import argparse
import re
from datetime import datetime




def handle_dates(start_date,end_date):
    '''Returns start and end datetime in int.
    Converts datetime to epoch to find correct buckets.

    Keyword arguments:
    start_date -- start date ("%Y-%m-%d %H:%M:%S")
    end_date -- end date ("%Y-%m-%d %H:%M:%S")
    '''
    epoch_time = []
    for date in [start_date,end_date]:
        date = time.strptime(date, "%Y-%m-%d %H:%M:%S")
        epoch_time.append(int(time.mktime(date).__str__().split(".")[0]))
    start_epoch_time = epoch_time[0]
    end_epoch_time = epoch_time[1]
    return start_epoch_time, end_epoch_time

def find_buckets(source_path, start_epoch_time, end_epoch_time):
    '''Returns the list buckets_found.
    Finds buckets in source path according to start and end epoch time.

    Keyword arguments:
    source_path -- archive path (frozendb)
    start_epoch_time -- start date
    end_epoch_time -- end date
    '''
    bucket_list = os.listdir(source_path)
    buckets_found = []
    for i in bucket_list:
        bucket = i.split("_", maxsplit=3)
        end = int(bucket[1])
        start = int(bucket[2])
        if (end > start or start == end) and (start >= start_epoch_time and end <= end_epoch_time):
            buckets_found.append(i)
    print("---------------------------")
    print("The number of buckets found: {}.".format(len(buckets_found)))
    return buckets_found


def move_buckets(source_path, dest_path,buckets_found):
    '''Returns None.
    Moves buckets from source path (frozendb) to destination path (thaweddb).

    Keyword arguments:
    source_path -- archive path (frozendb)
    dest_path -- the path where the buckets are moved to rebuild (thaweddb)
    buckets_found -- buckets found
    '''
    print("---------------------------")
    print("Moving Buckets...")
    for bucket in buckets_found:
        source_file = source_path + bucket
        destination = dest_path + bucket
        shutil.copytree(source_file, destination)
    print("---------------------------")
    print("Buckets are successfully moved...")
    print("---------------------------")
    return None

def check_data_integrity(source_path, buckets_found, splunk_home):
    '''Returns buckets_found, buckets_failed_integrity, buckets_passed_integrity, buckets_not_checked_integrity.
    Checks the data integrity one by one in the source path (thaweddb).


    Keyword arguments:
    source_path -- archive path (frozendb)
    buckets_found -- buckets found
    splunk_home -- splunk home path
    '''
    path = os.getcwd()
    buckets_failed_integrity = []
    buckets_passed_integrity = []
    buckets_not_checked_integrity = []
    buckets_to_process = buckets_found
    for bucket in buckets_found:
        bucket_path = source_path + bucket + "/rawdata/"
        for filename in os.listdir(bucket_path):
            if not filename.startswith("l2Hash") and (int(len(os.listdir(bucket_path))<3)):
                buckets_not_checked_integrity.append(bucket)
            os.chdir(path)
    buckets_to_process = list(set(buckets_to_process) - set(buckets_not_checked_integrity))

    subprocess.run(["cd","{}".format((splunk_home + "/bin") or ("/opt/splunk/bin"))])
    for bucket in buckets_to_process:
        bucket_path = source_path + bucket
        intregrity_result = subprocess.check_output(["{}/bin/splunk {} -bucketPath {}".format(splunk_home, "check-integrity", bucket_path)], shell = True, stderr=subprocess.STDOUT, universal_newlines = True)
        print(intregrity_result)
        match = re.findall('succeeded=(\d),\sfailed=(\d)', intregrity_result)
        fail = int(match[0][1])
        success = int(match[0][0])
        if fail == 1:
            buckets_failed_integrity.append(bucket)
            print("Integrity check has failed for the bucket:", bucket)
            print("This bucket will be removed from rebuilding list...")
        else:
            buckets_passed_integrity.append(bucket)
    print("Data integrity is checked...")
    print("Results:")
    print("The number of buckets has failed:", len(buckets_failed_integrity))
    print("---------------------------")
    print("The number of buckets has succeed:", len(buckets_passed_integrity))
    print("---------------------------")
    print("The number of buckets have no data ingtegrity control:", len(buckets_not_checked_integrity))
    print("---------------------------")
    buckets_found = list(set(buckets_found) - set(buckets_failed_integrity))
    print("The number of buckets will be rebuild:", len(buckets_passed_integrity) + len(buckets_not_checked_integrity))
    print("---------------------------")
    os.chdir(path)
    return buckets_found, buckets_failed_integrity, buckets_passed_integrity, buckets_not_checked_integrity


def log_data_integrity(buckets_not_checked_integrity, buckets_failed_integrity, buckets_passed_integrity):
    '''Returns None.
    Creates a log file about failed, passed and buckets without data integrity control.


    Keyword arguments:
    buckets_not_checked_integrity -- buckets do not have data integrity control
    buckets_failed_integrity -- buckets failed the integrity check
    buckets_passed_integrity -- buckets passed the integrity check
    '''
    path = os.getcwd()
    os.chdir("logs/")
    file_name = datetime.now().strftime("%Y-%m-%d-%H-%M-%S_integrity_check.log")
    f = open(file_name, "w+")
    f.write("Timestamp: {}\r\n\r\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    f.write("------------------\r\n")
    f.write("  Buckets Failed  \r\n")
    f.write("------------------\r\n\r\n")
    for i, bucket in zip(range(len(buckets_failed_integrity)), buckets_failed_integrity):
        f.write("{}- {}\r\n".format(i+1,bucket))
    f.write("\r\n\r\n\r\n")
    f.write("------------------\r\n")
    f.write("  Buckets Passed  \r\n")
    f.write("------------------\r\n\r\n")
    for i, bucket in zip(range(len(buckets_passed_integrity)), buckets_passed_integrity):
        f.write("{}- {}\r\n".format(i+1,bucket))
    f.write("\r\n\r\n\r\n")
    f.write("----------------------------------------\r\n")
    f.write("  Buckets Have No Data Integrity Check  \r\n")
    f.write("----------------------------------------\r\n\r\n")
    for i, bucket in zip(range(len(buckets_not_checked_integrity)), buckets_not_checked_integrity):
        f.write("{}- {}\r\n".format(i+1,bucket))
    f.close()
    os.chdir(path)
    return None

def rebuild_buckets(buckets_found, dest_path, dest_index, splunk_home):
    '''Returns failed and passed buckets.
    Rebuilds the buckets one by one in the destination path (thaweddb).

    Keyword arguments:
    buckets_found -- buckets found
    dest_path -- the path where the buckets are moved to rebuild (thaweddb)
    dest_index -- the index name where the buckets will be rebuilt
    splunk_home -- splunk home path
    '''
    buckets_failed = []
    buckets_passed = []
    path = os.getcwd()
    subprocess.run(["cd","{}".format((splunk_home + "/bin") or ("/opt/splunk/bin"))], stdout=subprocess.PIPE)
    for bucket in buckets_found:
        try:
            rebuild_result = subprocess.check_output(["{}/bin/splunk rebuild {}{} {}".format(splunk_home, dest_path, bucket, dest_index)], shell = True, universal_newlines = True)
            buckets_passed.append(bucket)
        except:
            buckets_failed.append(bucket)
            pass
    os.chdir(path)
    print("Buckets are rebuilt...")
    print("---------------------------")
    print("The number of buckets that rebuilt successfully:", len(buckets_passed))
    print("---------------------------")
    print("The number of buckets that failed to rebuild:", len(buckets_failed))
    print("---------------------------")
    return buckets_passed, buckets_failed

def log_rebuilt_results(buckets_passed, buckets_failed):
    '''Returns None.
    Logs the failed and passed buckets names.

    Keyword arguments:
    buckets_passed -- buckets that are rebuilt successfully
    buckets_failed -- buckets that failed the rebuilding process

    '''
    os.chdir("logs/")
    file_name = datetime.now().strftime("%Y-%m-%d-%H-%M-%S_buckets_rebuilt.log")
    f = open(file_name, "w+")
    f.write("Timestamp: {}\r\n\r\n".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    f.write("--------------------------------\r\n")
    f.write("  Buckets Successfully Rebuilt \r\n")
    f.write("-------------------------------\r\n\r\n")
    for i, bucket in zip(range(len(buckets_passed)), buckets_passed):
        f.write("{}- {}\r\n".format(i+1,bucket))
    f.write("\r\n\r\n\r\n")
    f.write("-----------------------------\r\n")
    f.write("  Buckets Failed to Rebuild \r\n")
    f.write("-----------------------------\r\n\r\n")
    for i, bucket in zip(range(len(buckets_failed)), buckets_failed):
        f.write("{}- {}\r\n".format(i + 1, bucket))
    f.close()
    return None


def restart_splunk(splunk_home):
    '''Returns None.
    Restarts the Splunk instance.

    Keyword arguments:
    splunk_home -- splunk home path
    '''
    print("Restarting Splunk now...")
    subprocess.run(["cd", "{}".format((splunk_home + "/bin") or ("/opt/splunk/bin"))])
    restart_result = subprocess.check_output("{}/bin/{}".format(splunk_home, "splunk restart"), shell=True, universal_newlines=True)
    print(restart_result)
    return None

def archive_help():
    '''Returns None.
    The argparse module also automatically generates help and usage.

    '''

    example_text = ''' example:

    archive_path:   "/opt/splunk/var/lib/splunk/wineventlog/frozendb/"
    restore_path:   "/opt/splunk/var/lib/splunk/archive_wineventlog/thaweddb/"
    restore_index:  "archive_wineventlog"
    start_date:     "Datetime format "%Y-%m-%d %H:%M:%S""
    end_date:       "Datetime format "%Y-%m-%d %H:%M:%S""
    splunk_home:    "/opt/splunk"

    python3 splunk_restore_archive.py  -a "/opt/splunk/var/lib/splunk/wineventlog/frozendb/" -r "/opt/splunk/var/lib/splunk/archive_wineventlog/thaweddb/"
    -i "archive_wineventlog" -s "2021-03-13 00:00:00" -e "2021-03-16 00:00:00" -sh "/opt/splunk" --restart_splunk --check_integrity

    python3 splunk_restore_archive.py  --archive_path "/opt/splunk/var/lib/splunk/wineventlog/frozendb/" --restore_path "/opt/splunk/var/lib/splunk/archive_wineventlog/thaweddb/"
    --restore_index "archive_wineventlog" --start_date "2021-03-13 00:00:00" --end_date "2021-03-16 00:00:00" --splunk_home "/opt/splunk"

    python3 splunk_restore_archive.py  -a="/opt/splunk/var/lib/splunk/wineventlog/frozendb/" -r="/opt/splunk/var/lib/splunk/archive_wineventlog/thaweddb/"
    -i="archive_wineventlog" -s="2021-03-13 00:00:00" -e="2021-03-16 00:00:00" -sh="/opt/splunk"  --check_integrity

    python3 splunk_restore_archive.py  --archive_path="/opt/splunk/var/lib/splunk/wineventlog/frozendb/" --restore_path="/opt/splunk/var/lib/splunk/archive_wineventlog/thaweddb/"
    --restore_index="archive_wineventlog" --start_date="2021-03-13 00:00:00" --end_date="2021-03-16 00:00:00" --splunk_home="/opt/splunk" --restart_splunk
    '''

    parser = argparse.ArgumentParser(epilog=example_text, formatter_class=argparse.RawDescriptionHelpFormatter)
    required_args = parser.add_argument_group("arguments")
    required_args.add_argument("-a","--archive_path", type=str, help="Archive path where the frozen buckets are")
    required_args.add_argument("-r", "--restore_path", type=str, help="The path where the frozen buckets are moved to rebuild")
    required_args.add_argument("-i", "--restore_index", type=str, help="The index name where the buckets are rebuilt")
    required_args.add_argument("-s", "--start_date", type=str, help="The starting date of the logs to be returned from the archive")
    required_args.add_argument("-e", "--end_date", type=str, help="The end date of logs to be returned from the archive")
    required_args.add_argument("-sh", "--splunk_home", type=str,help="Splunk home path")
    parser.add_argument("--restart_splunk", action='store_const', const=restart_splunk, help="Splunk needs to be restarted to complete the rebuilding process")
    parser.add_argument("--check_integrity", action='store_const', const=check_data_integrity, help="Checks the integrity of buckets to be rebuild")
    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')
    args = parser.parse_args()
    return args


def main():
    args = archive_help()
    start_epoch_time, end_epoch_time = handle_dates(args.start_date, args.end_date)
    buckets_found = find_buckets(args.archive_path, start_epoch_time, end_epoch_time)
    if args.check_integrity:
        buckets_found, buckets_failed_integrity, buckets_passed_integrity, buckets_not_checked_integrity = check_data_integrity(args.archive_path, buckets_found, args.splunk_home)
        log_data_integrity(buckets_not_checked_integrity, buckets_failed_integrity, buckets_passed_integrity)
    move_buckets(args.archive_path, args.restore_path, buckets_found)
    buckets_passed, buckets_failed = rebuild_buckets(buckets_found, args.restore_path, args.restore_index, args.splunk_home)
    log_rebuilt_results(buckets_passed, buckets_failed)
    if args.restart_splunk:
        restart_splunk(args.splunk_home)

if __name__ == "__main__":
    main()
