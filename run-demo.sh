#!/bin/bash

# ==============================================================================
# GCC Demo Management Script
# ==============================================================================
# Interactive script to plan, apply, and destroy demo configurations
# 
# Usage: ./run-demo.sh
# 
# Prerequisites:
# 1. Azure CLI logged in: az login
# 2. Terraform installed and in PATH
# 3. credentials.tfvars file configured with your Azure credentials
#
# Author: Jason Pang
# ==============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMOS_DIR="$SCRIPT_DIR/demos"
CREDENTIALS_FILE="$SCRIPT_DIR/credentials.tfvars"

# Demo configurations (compatible with bash 3.2+)
DEMO_KEYS=("arc" "vpn" "expressroute" "avd" "agentic" "hub-onprem" "hub-non-gen" "hub-non-gen-gen")
DEMO_VALUES=(
    "demos/arc/arc-demo.tfvars|Azure Arc Hybrid Management (OnPrem-Hub Setup)|~$150/month|30-40 minutes"
    "demos/vpn/vpn-demo.tfvars|Site-to-Site VPN Connectivity (OnPrem-Hub Setup)|~$1,250/month|45-60 minutes"
    "demos/expressroute/expressroute-demo.tfvars|ExpressRoute Private Connectivity (Hub Setup)|~$800-2,000/month|30-45 minutes"
    "demos/avd/avd-demo.tfvars|Azure Virtual Desktop with Enterprise Features (Hub-Non-Gen Setup)|~$1,070/month|45-60 minutes"
    "demos/agentic/eol-agentic-demo.tfvars|Agentic EOL Analysis App with Azure Arc and Azure OpenAI (OnPrem-Hub-Non-Gen Setup)|~$300/month|25-35 minutes"
    "demos/hub-spoke/hub-onprem-basic-demo.tfvars|Basic Hub-OnPrem Network Architecture|~\$0/month|<5 minutes"
    "demos/hub-spoke/hub-non-gen-basic-demo.tfvars|Basic Hub-Spoke Network Architecture|~\$0/month|<5 minutes"
    "demos/hub-spoke/hub-non-gen-gen-basic-demo.tfvars|Basic Hub-Spoke Network Architecture|~\$0/month|<5 minutes"
)

# Helper function to get demo info by key
get_demo_info() {
    local key="$1"
    local i
    for i in "${!DEMO_KEYS[@]}"; do
        if [[ "${DEMO_KEYS[$i]}" == "$key" ]]; then
            echo "${DEMO_VALUES[$i]}"
            return 0
        fi
    done
    return 1
}

# Functions
print_header() {
    local sep="=============================================================================="
    local title="GCC Demo Manager"
    local width=${#sep}
    local tlen=${#title}

    # Top separator in blue
    echo -e "${BLUE}${sep}"

    # Center the title between separators
    if (( tlen >= width )); then
        echo -e "${title}"
    else
        local pad_left=$(( (width - tlen) / 2 ))
        local pad_right=$(( width - tlen - pad_left ))
        local spaces_left="$(printf '%*s' "$pad_left" "")"
        local spaces_right="$(printf '%*s' "$pad_right" "")"
        printf "%s%s%s\n" "$spaces_left" "$title" "$spaces_right"
    fi

    # Bottom separator in blue and then reset color
    echo -e "${BLUE}${sep}${NC}"
    echo
}

print_separator() {
    echo -e "${CYAN}------------------------------------------------------------------------------${NC}"
}

check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"
    
    # Check if Terraform is installed
    if ! command -v terraform &> /dev/null; then
        echo -e "${RED}❌ Terraform is not installed or not in PATH${NC}"
        echo "Please install Terraform: https://www.terraform.io/downloads.html"
        exit 1
    fi
    
    # Check if Azure CLI is installed
    if ! command -v az &> /dev/null; then
        echo -e "${RED}❌ Azure CLI is not installed or not in PATH${NC}"
        echo "Please install Azure CLI: https://docs.microsoft.com/cli/azure/install-azure-cli"
        exit 1
    fi
    
    # Check if logged into Azure
    if ! az account show &> /dev/null; then
        echo -e "${RED}❌ Not logged into Azure CLI${NC}"
        echo "Please run: az login"
        exit 1
    fi
    
    # Check if credentials file exists
    if [ ! -f "$CREDENTIALS_FILE" ]; then
        echo -e "${RED}❌ credentials.tfvars file not found${NC}"
        echo "Please copy credentials.tfvars.example to credentials.tfvars and update with your values"
        echo "Run: cp credentials.tfvars.example credentials.tfvars"
        exit 1
    fi
    
    # Check if Terraform is initialized
    if [ ! -d "$SCRIPT_DIR/.terraform" ]; then
        echo -e "${YELLOW}⚠️  Terraform not initialized. Running 'terraform init'...${NC}"
        cd "$SCRIPT_DIR"
        terraform init
    fi
    
    echo -e "${GREEN}✅ All prerequisites met${NC}"
    echo
}

show_azure_info() {
    echo -e "${CYAN}Current Azure Context:${NC}"
    SUBSCRIPTION_NAME=$(az account show --query name -o tsv 2>/dev/null || echo "Unknown")
    SUBSCRIPTION_ID=$(az account show --query id -o tsv 2>/dev/null || echo "Unknown")
    echo "  Subscription: $SUBSCRIPTION_NAME"
    echo "  ID: $SUBSCRIPTION_ID"
    echo
}

show_demo_menu() {
    print_separator
    echo -e "${PURPLE}Available Demos:${NC}"
    echo
    
    local counter=1
    for demo_key in "${DEMO_KEYS[@]}"; do
        demo_info=$(get_demo_info "$demo_key")
        IFS='|' read -r path description cost time <<< "$demo_info"
        echo -e "${CYAN}$counter)${NC} ${GREEN}$description${NC}"
        echo "   Path: $path"
        echo "   Cost: $cost"
        echo "   Time: $time"
        echo
        ((counter++))
    done
    
    echo -e "${CYAN}0)${NC} ${RED}Exit${NC}"
    echo
}

show_action_menu() {
    local demo_name="$1"
    local demo_description="$2"
    
    print_separator
    echo -e "${PURPLE}Selected Demo:${NC} ${GREEN}$demo_description${NC}"
    echo
    echo -e "${CYAN}Actions:${NC}"
    echo "1) Plan   - Preview changes without applying"
    echo "2) Apply  - Deploy the demo infrastructure"
    echo "3) Destroy - Remove all demo resources"
    echo "4) Show Current State - Display Terraform state"
    echo "5) Show Outputs - Display Terraform outputs"
    echo "0) Back to demo selection"
    echo
}

get_demo_by_number() {
    local selection="$1"
    local counter=1
    
    for demo_key in "${DEMO_KEYS[@]}"; do
        if [ "$counter" -eq "$selection" ]; then
            echo "$demo_key"
            return
        fi
        ((counter++))
    done
    echo ""
}

run_terraform_command() {
    local action="$1"
    local demo_path="$2"
    local demo_description="$3"
    
    cd "$SCRIPT_DIR"
    
    case "$action" in
        "plan")
            echo -e "${YELLOW}Planning deployment for: $demo_description${NC}"
            echo -e "${CYAN}Command: terraform plan -var-file=\"$CREDENTIALS_FILE\" -var-file=\"$demo_path\"${NC}"
            echo
            terraform plan -var-file="$CREDENTIALS_FILE" -var-file="$demo_path"
            ;;
        "apply")
            echo -e "${YELLOW}Deploying: $demo_description${NC}"
            echo -e "${CYAN}Command: terraform apply -var-file=\"$CREDENTIALS_FILE\" -var-file=\"$demo_path\"${NC} --auto-approve"
            #echo
            #echo -e "${RED}⚠️  WARNING: This will create billable Azure resources!${NC}"
            #read -p "Are you sure you want to proceed? (yes/no): " confirm
            #if [ "$confirm" = "yes" ]; then
                terraform apply -var-file="$CREDENTIALS_FILE" -var-file="$demo_path" --auto-approve
                echo
                echo -e "${GREEN}✅ Deployment completed!${NC}"
                echo -e "${YELLOW}💡 Don't forget to destroy resources when done to avoid ongoing charges${NC}"
            #else
            #    echo -e "${YELLOW}Deployment cancelled${NC}"
            #fi
            ;;
        "destroy")
            echo -e "${YELLOW}Destroying: $demo_description${NC}"
            echo -e "${CYAN}Command: terraform destroy -var-file=\"$CREDENTIALS_FILE\" -var-file=\"$demo_path\"${NC}"
            echo
            echo -e "${RED}⚠️  WARNING: This will permanently delete all demo resources!${NC}"
            read -p "Are you sure you want to proceed? (yes/no): " confirm
            if [ "$confirm" = "yes" ]; then
                terraform destroy -var-file="$CREDENTIALS_FILE" -var-file="$demo_path"
                echo
                echo -e "${GREEN}✅ Resources destroyed successfully!${NC}"
            else
                echo -e "${YELLOW}Destruction cancelled${NC}"
            fi
            ;;
        "state")
            echo -e "${YELLOW}Current Terraform State:${NC}"
            terraform state list 2>/dev/null || echo "No resources in state"
            ;;
        "outputs")
            echo -e "${YELLOW}Terraform Outputs:${NC}"
            terraform output 2>/dev/null || echo "No outputs available"
            ;;
    esac
}

show_cost_warning() {
    local demo_key="$1"
    demo_info=$(get_demo_info "$demo_key")
    IFS='|' read -r path description cost time <<< "$demo_info"
    
    echo
    print_separator
    echo -e "${RED}💰 COST WARNING${NC}"
    echo -e "${YELLOW}Demo:${NC} $description"
    echo -e "${YELLOW}Estimated Cost:${NC} $cost"
    echo -e "${YELLOW}Deployment Time:${NC} $time"
    echo
    echo -e "${RED}This demo will create billable Azure resources!${NC}"
    echo -e "${YELLOW}Remember to destroy resources when finished to avoid ongoing charges.${NC}"
    print_separator
    echo
}

main() {
    print_header
    check_prerequisites
    show_azure_info
    
    while true; do
        show_demo_menu
        read -p "Select a demo (0-${#DEMO_KEYS[@]}): " demo_selection
        
        if [ "$demo_selection" = "0" ]; then
            echo -e "${GREEN}Goodbye!${NC}"
            exit 0
        fi
        
        demo_key=$(get_demo_by_number "$demo_selection")
        if [ -z "$demo_key" ]; then
            echo -e "${RED}Invalid selection. Please try again.${NC}"
            continue
        fi
        
        demo_info=$(get_demo_info "$demo_key")
        IFS='|' read -r demo_path demo_description cost time <<< "$demo_info"
        
        while true; do
            show_action_menu "$demo_key" "$demo_description"
            read -p "Select an action (0-5): " action_selection
            
            case "$action_selection" in
                "1")
                    run_terraform_command "plan" "$demo_path" "$demo_description"
                    echo
                    read -p "Press Enter to continue..."
                    ;;
                "2")
                    show_cost_warning "$demo_key"
                    run_terraform_command "apply" "$demo_path" "$demo_description"
                    echo
                    read -p "Press Enter to continue..."
                    ;;
                "3")
                    run_terraform_command "destroy" "$demo_path" "$demo_description"
                    echo
                    read -p "Press Enter to continue..."
                    ;;
                "4")
                    run_terraform_command "state" "$demo_path" "$demo_description"
                    echo
                    read -p "Press Enter to continue..."
                    ;;
                "5")
                    run_terraform_command "outputs" "$demo_path" "$demo_description"
                    echo
                    read -p "Press Enter to continue..."
                    ;;
                "0")
                    break
                    ;;
                *)
                    echo -e "${RED}Invalid selection. Please try again.${NC}"
                    ;;
            esac
        done
    done
}

# Handle script interruption
trap 'echo -e "\n${YELLOW}Script interrupted by user${NC}"; exit 1' INT

# Run main function
main "$@"
