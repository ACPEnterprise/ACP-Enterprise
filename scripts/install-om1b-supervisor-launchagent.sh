#!/bin/zsh
set -euo pipefail

om1b_script_dir=${0:A:h}
om1b_repo_root=${om1b_script_dir:h}
om1b_label=com.acp.om1b.engineering-supervisor
om1b_uid=$(/usr/bin/id -u)
om1b_user=$(/usr/bin/id -un)
om1b_domain=gui/${om1b_uid}
om1b_service=${om1b_domain}/${om1b_label}
om1b_agent_dir=/Users/${om1b_user}/Library/LaunchAgents
om1b_agent_path=${om1b_agent_dir}/${om1b_label}.plist
om1b_template=${om1b_repo_root}/docs/engineering/launchd/${om1b_label}.plist.template
om1b_state_dir=${om1b_repo_root}/.development-factory/om1b
om1b_runtime=${om1b_state_dir}/runtime.json
om1b_stop=${om1b_state_dir}/runtime.json.stop

if [[ ! -f ${om1b_template} || ! -f ${om1b_runtime} ]]; then
  print -u2 "OM1-B supervisor template or runtime checkpoint is missing."
  exit 66
fi

if /bin/launchctl print ${om1b_service} >/dev/null 2>&1; then
  print -u2 "${om1b_label} is already registered; refusing a duplicate installation."
  exit 73
fi

/bin/mkdir -p ${om1b_agent_dir} ${om1b_state_dir}
umask 077
om1b_rendered=$(/usr/bin/mktemp ${TMPDIR:-/tmp}/om1b-launchagent.XXXXXX)
trap '/bin/rm -f ${om1b_rendered}' EXIT
/usr/bin/sed "s|__REPO_ROOT__|${om1b_repo_root}|g" ${om1b_template} >${om1b_rendered}
/usr/bin/plutil -lint ${om1b_rendered} >/dev/null
/usr/bin/install -m 600 ${om1b_rendered} ${om1b_agent_path}

# Request a bounded, checkpointed exit from the existing managed supervisor.
: >${om1b_stop}
om1b_wait_count=0
while (( om1b_wait_count < 90 )); do
  om1b_active_pid=$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("active_pid") or "")' ${om1b_runtime})
  [[ -z ${om1b_active_pid} ]] && break
  /bin/sleep 1
  (( om1b_wait_count += 1 ))
done

if [[ -n ${om1b_active_pid:-} ]]; then
  print -u2 "Existing supervisor did not clear its checkpoint; launchd was not started."
  exit 75
fi

/bin/rm -f ${om1b_stop}
/bin/launchctl bootstrap ${om1b_domain} ${om1b_agent_path}
/bin/launchctl enable ${om1b_service}

om1b_health_count=0
while (( om1b_health_count < 30 )); do
  om1b_new_pid=$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("active_pid") or "")' ${om1b_runtime})
  [[ -n ${om1b_new_pid} ]] && break
  /bin/sleep 1
  (( om1b_health_count += 1 ))
done

if [[ -z ${om1b_new_pid:-} ]]; then
  print -u2 "LaunchAgent registered but no active supervisor PID was checkpointed."
  exit 70
fi

print "Installed ${om1b_label}; active supervisor PID ${om1b_new_pid}."
/bin/launchctl print ${om1b_service} | /usr/bin/sed -n '1,35p'
