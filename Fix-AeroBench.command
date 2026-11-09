#!/bin/bash
# App-specific repair for the locally installed AeroBench bundles.
# Does not disable Gatekeeper globally or change scans, keys, or results.
set -euo pipefail
if [[ "$(/usr/bin/uname -s)" != Darwin ]]; then
  echo 'This repair must run on your Mac.' >&2
  exit 1
fi
umask 077
mkdir -p "$HOME/Library/Logs/AeroBench"
repair_log="$HOME/Library/Logs/AeroBench/launch-repair.log"
exec > >(tee -a "$repair_log") 2>&1
echo "AeroBench launch repair — $(date)"
apps=()
launch_app=''
for folder in /Applications "$HOME/Applications"; do
  for name in AeroBench.app AeroBench-Connect.app 'AeroBench Connect.app'; do
    candidate="$folder/$name"
    [[ -d "$candidate" && ! -L "$candidate" ]] || continue
    bundle_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$candidate/Contents/Info.plist" 2>/dev/null) || continue
    case "$bundle_id" in
      com.aerobench.desktop|com.aerobench.connect) ;;
      *) echo "Skipping unexpected app identity: $candidate"; continue ;;
    esac
    apps+=("$candidate")
    if [[ -z "$launch_app" || "$bundle_id" == com.aerobench.connect ]]; then
      launch_app="$candidate"
    fi
  done
done
if [[ ${#apps[@]} -eq 0 ]]; then
  echo 'No installed AeroBench app found. Move AeroBench.app and AeroBench Connect into Applications, then run this repair again.'
  exit 1
fi
for app in "${apps[@]}"; do
  echo "Checking $app"
  if ! /usr/bin/codesign --verify --strict --verbose=2 "$app"; then
    echo 'Rebuilding this app’s local ad-hoc signature using macOS codesign.'
    /usr/bin/codesign --force --sign - "$app" || {
      echo 'Signature repair failed. No app will be launched. Send launch-repair.log for diagnosis.'
      exit 1
    }
    /usr/bin/codesign --verify --strict --verbose=2 "$app" || exit 1
  fi
  # Remove only this app's download quarantine, after signature verification.
  if /usr/bin/xattr -r "$app" | /usr/bin/grep com.apple.quarantine >/dev/null; then
    /usr/bin/xattr -rd com.apple.quarantine "$app" || {
      echo 'Could not update this app’s quarantine attribute. Check that your account can modify it in Applications.'
      exit 1
    }
  fi
done
echo "Opening $launch_app"
/usr/bin/open "$launch_app"
echo "Launch requested. Diagnostic log: $repair_log"
