#!/bin/bash

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

LOG_FILE="run.log"

echo -e "${BLUE}======================================================================${NC}"
echo -e "${BLUE}                   VIDEO PIPELINE STATUS REPORT                       ${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo ""

# 1. Check Processes
echo -e "${BLUE}--- 1. Running Processes ---${NC}"
pipeline_procs=$(ps aux | grep -E "run_pipeline|front_window|deck|sewing_room|dvr-scan|filter_clips" | grep -v grep)

if [ -z "$pipeline_procs" ]; then
    echo -e "  Status: ${RED}NOT RUNNING${NC}"
else
    echo -e "  Status: ${GREEN}RUNNING${NC}"
    echo "  Process Details:"
    echo "$pipeline_procs" | awk '{printf "    PID %-8s | CPU %-5s%% | MEM %-5s%% | %s\n", $2, $3, $4, substr($0, index($0,$11))}' | head -n 10
fi
echo ""

# 2. Check Progress Log
echo -e "${BLUE}--- 2. Log Progress (run.log) ---${NC}"
if [ -f "$LOG_FILE" ]; then
    echo -e "  ${YELLOW}Latest log updates:${NC}"
    # Replace carriage returns with newlines and grab last 15 lines
    tr '\r' '\n' < "$LOG_FILE" | tail -n 15 | sed 's/^/    /'
else
    echo -e "  ${RED}Log file not found at $LOG_FILE${NC}"
fi

echo ""
echo -e "${BLUE}======================================================================${NC}"
