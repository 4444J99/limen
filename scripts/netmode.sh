#!/bin/bash
# ============================================================================
# netmode — multi-link manager for a laptop across metered + free connections:
#   📱 iPhone hotspot  300 GB, resets the 13th (Verizon; laptop is its only user → meter exact)
#   🛰 Starlink        1000 GB, resets the 28th (shared with the TV → anchor to provider #)
#   🆓 any other Wi-Fi  uncapped/free — tracked for info, never billed
# Each metered link has its OWN cap + OWN reset day. Caps are shared across devices, so the
# carrier/Starlink figure is ground truth: `netmode setusage <phone|starlink> <GB>` anchors it.
#
# Modes:
#   observe   meter/report only; background timers never switch networks [default]
#   auto      burn the phone first, auto-fall to Starlink at the cap   [smart]
#   failover  cable=phone, unplug=Starlink (instant)
#   anchor    Starlink first even when plugged (save the phone)
#   solo      phone only, never Starlink (phone-WiFi ok; offline if phone gone)
#   ladder    phone-USB → phone-WiFi → Starlink
#   phone     one-shot: grab the iPhone hotspot right now (blip-free)
#
# Other commands:
#   netmode                 live status (text) + "Next move"
#   netmode watch [secs]    live auto-refreshing status (Ctrl-C to quit)
#   netmode why             explain the current decision + the inputs behind it
#   netmode report          usage + projection
#   netmode doctor          full diagnostic (links, scores, schedule, service order)
#   netmode export          usage history as CSV (stdout)
#   netmode setusage L GB   anchor link L (phone|starlink) to a provider-reported GB number
#   netmode menubar install drop a SwiftBar/xbar menu-bar plugin (opt-in, no daemon)
#   netmode json            machine status (used by the dashboard)
#   netmode selftest        assert decision logic & invariants (no network changes)
#   netmode ui              open the dashboard
#   netmode tick            internal: run every 5 min by launchd
#   netmode stop            disable every netmode/netmeter launch agent (no network changes)
#
# Schedules: schedule.tsv lines "HHMM HHMM mode" (wrap-around ok). Empty = no rules.
#   Edited via the dashboard; on a window edge the schedule takes over, restoring
#   your base mode when the window ends. e.g. "0100 0700 anchor" = Starlink overnight.
#
# No sudo. No password stored on disk (Wi-Fi re-homes via keychain/power-cycle).
# ============================================================================

DIR="$HOME/Library/Application Support/netmeter"
CONFIG="$DIR/config"
MODEFILE="$DIR/mode"
AUTOSTATE="$DIR/auto_state"
STATE="$DIR/state"
USAGE="$DIR/usage.tsv"
HISTORY="$DIR/history.tsv"
EVENTS="$DIR/events.log"
HEALTH="$DIR/health"
NOTIFY="$DIR/notify_state"
DEADCNT="$DIR/deadlink_count"
PROBECNT="$DIR/probe_count"
LOCK="$DIR/.switching"
LOCKD="$DIR/.switching.d"        # atomic (mkdir) single-flight lock for apply_mode
DESIRED="$DIR/desired_mode"      # latest requested mode (last-writer-wins)
GENFILE="$DIR/switch_gen"        # monotonically-bumped switch generation
HEALTHTSV="$DIR/health.tsv"      # rolling per-link latency+loss samples
SCHEDULE="$DIR/schedule.tsv"     # time-of-day rules: "HHMM HHMM mode" (empty = none)
SCHEDWIN="$DIR/sched_window"     # last schedule window we were inside (edge detection)
HOME_FP="$DIR/home_fingerprint"  # learned set of Wi-Fi SSIDs habitually visible at home
LOCSTATE="$DIR/location_state"   # debounced location: "committed pending pendcount"
LOC_OVERRIDE="$DIR/loc_override" # manual home/away pin: "home|away epoch_expiry"
MIGRATED="$DIR/.seamless_migrated"  # one-time flag: old 'auto' default flipped to 'seamless'
_SEAMHOLD="$DIR/seamless_hold"   # throttle the "phone left, holding offline" notice (once per absence)
ANCHORWIN="$DIR/anchor_window"   # overnight Starlink window "HHMM HHMM" (empty/absent = off); HOME-only sub-rule of seamless
_ANCHORSAID="$DIR/anchor_announced" # one-time flag: announced the overnight anchor is active
_ANCHORFAIL="$DIR/anchor_fail"      # per-window backoff: Starlink unreachable this window -> don't power-cycle Wi-Fi every tick
ANCHORSEED="$DIR/.anchor_seeded"    # one-time flag: seeded the default overnight window (existing installs too)
SENSE="$DIR/sense_cache"         # tick-written cache "location<TAB>presence<TAB>starlink_vis" for fast json/dashboard

# ---- config (defaults, overridden by $CONFIG) ------------------------------
# Each metered link has its OWN cap and its OWN billing reset day (they differ!):
#   📱 iPhone hotspot = 300 GB, resets the 13th (Verizon; the laptop is its only user → meter is exact)
#   🛰 Starlink       = 1000 GB, resets the 28th (shared with the TV → meter undercounts; anchor to provider #)
# Any OTHER network (friend's Wi-Fi, café, etc.) is "free": tracked for info, never counted against a cap.
PHONE_CAP_GB=300;  PHONE_RESET_DAY=13
STARLINK_CAP_GB=1000; STARLINK_RESET_DAY=28
RESET_DAY=1; AUTO_SWITCH=1                  # RESET_DAY kept for the 'free' bucket / back-compat
BACKGROUND_SWITCHING=0                      # launchd ticks observe by default; explicit CLI commands switch
WARN_PCT=80; CRIT_PCT=95; AUTO_RECOVER=1
RECYCLE_CLIENTS=1                            # on a gateway change, recycle long-lived clients (drop stale sockets)
RECYCLE_LABELS="com.limen.heartbeat"        # space-sep launchd labels to kickstart on net switch
STARLINK_SSID="MY_STARLINK_SSID"; PHONE_SSID="MY_PHONE_HOTSPOT_SSID"   # publish-safe placeholders; real values live in the untracked $CONFIG (sourced below)
PHONE_GW="172.20.10.1"; STARLINK_GW="192.168.1.1"; WIFI_IF="en0"; USB_IF="en8"; DASH_PORT=8765
DISH_GW="192.168.100.1"; DISH_GPORT=9200; DISHCACHE="$DIR/dish_status.json"; DISH_TTL=30  # Starlink dish gRPC (read-only diagnostic)
PHONE_BT_NAME="MY_PHONE_HOTSPOT_SSID"   # iPhone Bluetooth device name (proximity); publish-safe placeholder, real value in $CONFIG
HOME_MIN_OVERLAP=2                 # how many learned home SSIDs must be visible to call it "home" (fingerprint)
LOC_OVERRIDE_HOURS=4               # how long a manual `netmode here|out` pin lasts before sensing resumes
LEAVE_HOME_SAMPLES=3               # asymmetric hysteresis: leaving home (re-permits Starlink) needs MORE proof than entering (2)
STRONG_AWAY_MIN=6                  # a healthy foreign scan (>=this many SSIDs, 0 home-overlap, no Starlink) = unambiguously away -> leave home in ONE sample
HOME_FP_MAX=200                    # cap on learned home-fingerprint SSIDs, so it can't grow without bound toward false-home
# ubiquitous public/carrier SSIDs that appear everywhere -> never learned as home anchors (would cause false-home away)
UBIQUITOUS_SSIDS='^(xfinitywifi|XFINITY|CableWiFi|attwifi|AT&T Wi-?Fi|optimumwifi|SpectrumWiFi.*|Spectrum Mobile|TWCWiFi.*|Boingo.*|eduroam|Google Starbucks|GoogleGuest|T-?Mobile.*|tmobile.*|Verizon Wi-?Fi|<redacted>|Free ?WiFi|Guest|Public ?WiFi|_?Free_?Wifi)$'
# hotspot keep-alive: iOS Personal Hotspot idle-disconnects after ~90s of no traffic (kills USB + Wi-Fi
# tether alike). A tiny heartbeat under that window stops the drops — but ONLY while the phone is the
# active link AND you're actually at the Mac, so it never wastes data/battery when idle or away.
KEEPALIVE_IDLE_MAX=240   # seconds of no keyboard/mouse before we let the hotspot nap (you've stepped away)
KEEPALIVE_HOST="1.1.1.1" # heartbeat target — external so it counts as real activity to the phone (~84B/beat)
[ -f "$CONFIG" ] && . "$CONFIG"
WIFI="$WIFI_IF"; USBIF="$USB_IF"; STARLINK="$STARLINK_SSID"

# ---- network primitives (proven) -------------------------------------------
order_phone_first() { networksetup -ordernetworkservices "iPhone USB" "USB 10/100/1000 LAN" "Thunderbolt Bridge" "Wi-Fi" >/dev/null 2>&1; }
order_wifi_first()  { networksetup -ordernetworkservices "Wi-Fi" "iPhone USB" "USB 10/100/1000 LAN" "Thunderbolt Bridge" >/dev/null 2>&1; }
enable_links()      { networksetup -setnetworkserviceenabled "iPhone USB" on >/dev/null 2>&1; networksetup -setnetworkserviceenabled "Wi-Fi" on >/dev/null 2>&1; }

wifi_on()  { networksetup -setairportpower "$WIFI" on >/dev/null 2>&1
  local i; for i in 1 2 3 4 5; do [ "$(networksetup -getairportpower "$WIFI" 2>/dev/null | awk '{print $NF}')" = On ] && break; sleep 1; done; sleep 3; }
wifi_off() { networksetup -setairportpower "$WIFI" off >/dev/null 2>&1; }

current_ssid() { ipconfig getsummary "$WIFI" 2>/dev/null | awk -F': ' '/ SSID/{print $2; exit}'; }
usb_up()       { [ -n "$(ipconfig getifaddr "$USBIF" 2>/dev/null)" ]; }
wifi_ip()      { ipconfig getifaddr "$WIFI" 2>/dev/null; }
on_phone_wifi(){ case "$(wifi_ip)" in 172.20.10.*) return 0;; *) return 1;; esac; }
on_starlink()  { local ip; ip=$(wifi_ip); [ -n "$ip" ] && ! on_phone_wifi; }
ssid_visible() { system_profiler SPAirPortDataType 2>/dev/null | grep -qF "$1:"; }

ensure_starlink_standby() {  # password-free: power-cycle, let macOS auto-rejoin Starlink
  wifi_on; on_starlink && return 0
  networksetup -setairportpower "$WIFI" off >/dev/null 2>&1; sleep 3
  networksetup -setairportpower "$WIFI" on  >/dev/null 2>&1
  local i; for i in 1 2 3 4 5 6 7 8; do sleep 4; on_starlink && return 0; done; return 1
}

pref_has()    { networksetup -listpreferredwirelessnetworks "$WIFI" 2>/dev/null | sed 's/^[[:space:]]*//' | grep -qxF "$1"; }
pref_add_top(){ pref_has "$1" || networksetup -addpreferredwirelessnetwork "$WIFI" "$1" 0 >/dev/null 2>&1; }
pref_remove() { pref_has "$1" && networksetup -removepreferredwirelessnetwork "$WIFI" "$1" >/dev/null 2>&1; }
pref_starlink_only()   { pref_remove "$PHONE_SSID"; pref_add_top "$STARLINK"; }
pref_phone_then_star() { pref_add_top "$STARLINK"; pref_add_top "$PHONE_SSID"; }

join() {
  local ssid="$1" i pw
  [ "$(current_ssid)" = "$ssid" ] && [ -n "$(wifi_ip)" ] && return 0
  for i in 1 2; do networksetup -setairportnetwork "$WIFI" "$ssid" >/dev/null 2>&1; sleep 6
    [ -n "$(wifi_ip)" ] && [ "$(current_ssid)" = "$ssid" ] && return 0; done
  if [ -t 0 ]; then printf 'Wi-Fi password for "%s": ' "$ssid" >&2; read -rs pw; printf '\n' >&2
    for i in 1 2; do networksetup -setairportnetwork "$WIFI" "$ssid" "$pw" >/dev/null 2>&1; sleep 6
      [ -n "$(wifi_ip)" ] && [ "$(current_ssid)" = "$ssid" ] && return 0; done; fi
  return 1
}

# ---- mode configs (network only; no mode-file write) -----------------------
# burn-phone-first: ride the phone by USB OR its Wi-Fi hotspot; Starlink only if phone is truly gone
PROBE_EVERY=6   # when parked on Starlink w/o USB, only re-probe the phone hotspot every N ticks (~30 min) to avoid blips
cfg_phone_first() {   # $1=force -> skip the Starlink-parked throttle and probe the phone right now
  order_phone_first; enable_links; wifi_on; pref_phone_then_star
  on_phone_wifi && { rm -f "$PROBECNT" 2>/dev/null; return 0; }   # already on phone hotspot -> done
  if usb_up; then
    # USB carries phone data and keeps the hotspot awake -> joining Wi-Fi causes NO blip (cable covers the gap).
    # Park Wi-Fi on the hotspot too, so an unplug stays on phone instead of dropping to Starlink.
    join "$PHONE_SSID" >/dev/null 2>&1; rm -f "$PROBECNT" 2>/dev/null; return 0
  fi
  # No USB. A phone-join attempt briefly drops Wi-Fi; if we're already online via Starlink, throttle probes so we
  # don't blip the connection every tick hunting for a phone that's away (its hotspot Wi-Fi sleeps when no client).
  if on_starlink && [ "$1" != force ]; then
    local c=0; [ -f "$PROBECNT" ] && c=$(cat "$PROBECNT"); c=$((c+1))
    if [ "$c" -lt "$PROBE_EVERY" ]; then echo "$c" > "$PROBECNT"; return 0; fi   # stay on Starlink, count toward next probe
  fi
  rm -f "$PROBECNT" 2>/dev/null
  join "$PHONE_SSID" >/dev/null 2>&1 && { log_event "auto → iPhone (hotspot reachable)"; return 0; }
  on_starlink || ensure_starlink_standby >/dev/null 2>&1   # phone unreachable -> stay/return to Starlink
}
cfg_failover() { order_phone_first; enable_links; wifi_on; pref_starlink_only; ensure_starlink_standby >/dev/null 2>&1; }
cfg_anchor()   { order_wifi_first;  enable_links; wifi_on; pref_starlink_only; ensure_starlink_standby >/dev/null 2>&1; }
cfg_solo()     { order_phone_first; networksetup -setnetworkserviceenabled "iPhone USB" on >/dev/null 2>&1
                 # "only the iPhone, never Starlink": drop Starlink from preferred so it won't auto-join, and
                 # cut Wi-Fi only if it's actually ON Starlink. Phone-over-Wi-Fi stays up (still phone data).
                 pref_remove "$STARLINK"; on_starlink && wifi_off; return 0; }
cfg_ladder()   { order_phone_first; enable_links; wifi_on; pref_phone_then_star; }

# seamless = the no-thinking policy. It asks WHERE it is and acts:
#   HOME  -> iPhone only; Starlink removed from auto-join (it's the TV's), never used even if the
#            phone leaves. Phone gone -> hold offline (cut Wi-Fi if it drifted to Starlink); the
#            phone returning (cable plug or next probe) reconnects automatically. `netmode out`
#            overrides for the rare miss.
#   AWAY  -> the proven auto cascade (burn phone first, fall to Starlink on cap / when phone gone).
#   UNKNOWN (Wi-Fi off / nothing sensed yet) -> conservative auto behavior.
cfg_seamless() {
  local loc; loc=$(location_cached)   # tick/do_seamless run sense_refresh first, so this is fresh
  case "$loc" in
    home)
      if in_anchor_window "$(date +%H%M)"; then
        # overnight window (user-set, default 0100–0700): ride Starlink so backups don't burn the
        # phone cap. HOME-gated — the away/unknown branch never reaches here, so it can't strand you
        # while traveling. Window closes -> next tick falls through to normal phone-only home logic.
        on_starlink && { rm -f "$_SEAMHOLD" "$_ANCHORFAIL" 2>/dev/null; return 0; }   # already on Starlink -> no thrash
        # Try Starlink at most ONCE per window. cfg_anchor power-cycles Wi-Fi to let macOS auto-join
        # Starlink; if it can't (e.g. no saved Starlink creds on this Mac), running it every tick
        # storms the Wi-Fi off/on endlessly. On a miss, mark the window failed and fall through to the
        # normal phone-only home path — a working iPhone link beats a doomed Starlink hunt. The flag
        # is cleared whenever we're outside the window, so each night gets one fresh attempt.
        if [ ! -f "$_ANCHORFAIL" ]; then
          if cfg_anchor; then
            rm -f "$_SEAMHOLD" 2>/dev/null
            _anchor_announce_once; log_event "seamless/home → overnight anchor (Starlink for backups)"; return 0
          fi
          : > "$_ANCHORFAIL"
          notify "Overnight anchor: couldn't reach Starlink" "Staying on iPhone tonight (Starlink not joinable on this Mac) · \`netmode overnight off\` to disable"
          log_event "seamless/home → anchor could not reach Starlink; falling back to iPhone (no Wi-Fi thrash)"
        fi
        # fall through to normal phone-only home logic below (no return)
      else
        rm -f "$_ANCHORFAIL" 2>/dev/null   # outside the window -> arm a fresh attempt for next window
      fi
      order_phone_first; enable_links; wifi_on; pref_remove "$STARLINK"   # OS won't auto-join Starlink at home
      on_phone_wifi && { rm -f "$PROBECNT" "$_SEAMHOLD" 2>/dev/null; return 0; }
      usb_up && { join "$PHONE_SSID" >/dev/null 2>&1; rm -f "$PROBECNT" "$_SEAMHOLD" 2>/dev/null; return 0; }
      join "$PHONE_SSID" >/dev/null 2>&1 && { rm -f "$PROBECNT" "$_SEAMHOLD" 2>/dev/null; log_event "seamless/home → iPhone hotspot"; return 0; }
      # couldn't reach the phone at home -> NEVER fall to Starlink. Cut Wi-Fi if it landed on Starlink.
      on_starlink && wifi_off
      [ "$(phone_present)" = gone ] && _seamless_hold_notify
      return 0 ;;
    *)  # away / unknown: the existing smart cascade (this is correct OUTSIDE the apartment)
      rm -f "$_SEAMHOLD" 2>/dev/null; auto_apply ;;
  esac
}
_seamless_hold_notify() {
  [ -f "$_SEAMHOLD" ] && return 0
  : > "$_SEAMHOLD"
  notify "Phone left — holding offline" "Starlink stays reserved for the TV · run \`netmode out\` to allow it"
  log_event "seamless/home: phone gone → holding (Starlink reserved for TV)"
}
_anchor_announce_once() {  # first time the overnight window grabs Starlink, say so (never a silent grab)
  [ -f "$_ANCHORSAID" ] && return 0
  : > "$_ANCHORSAID"
  local s e; [ -s "$ANCHORWIN" ] && read -r s e < "$ANCHORWIN"
  notify "Overnight anchor active" "Riding Starlink ${s:-overnight}–${e} so backups don't burn the phone cap · \`netmode overnight off\` to disable"
}

save_mode() { printf '%s\n' "$1" > "$MODEFILE"; }
# observe is the default. Background timers must not move a live machine between networks unless the
# operator explicitly opts in with BACKGROUND_SWITCHING=1 in $CONFIG.
do_observe() { save_mode observe; log_event "mode → observe"; }

# Older installs migrated the default to "seamless", which was too aggressive for live sessions:
# it could remove Starlink from preferred networks and force the iPhone at home. Migrate old
# default-like modes to observe once; leave explicitly directional modes alone.
OBSERVE_MIGRATED="$DIR/.observe_default_migrated"
migrate_default() {
  if [ ! -f "$OBSERVE_MIGRATED" ]; then
    : > "$OBSERVE_MIGRATED"
    case "$(cat "$MODEFILE" 2>/dev/null)" in
      ""|auto|seamless) printf 'observe\n' > "$MODEFILE" ;;
    esac
  fi
  # seed the user's stated overnight exception once (Backblaze/Time Machine ride Starlink, not the phone
  # cap). Own one-time marker so EXISTING installs (already past the mode migration) still get it. `overnight
  # off` leaves an empty file, so this never re-enables behind the user's back.
  if [ ! -f "$ANCHORSEED" ]; then : > "$ANCHORSEED"; [ -f "$ANCHORWIN" ] || printf '0100 0700\n' > "$ANCHORWIN"; fi
}
get_mode()  { [ -f "$MODEFILE" ] && cat "$MODEFILE" || echo "observe"; }

do_failover(){ cfg_failover; save_mode failover; log_event "mode → failover"; }
do_anchor()  { cfg_anchor;   save_mode anchor;   log_event "mode → anchor"; }
do_solo()    { cfg_solo;     save_mode solo;     log_event "mode → solo"; }
do_ladder()  { cfg_ladder;   save_mode ladder;   log_event "mode → ladder"; enforce; }
do_auto()    { save_mode auto; log_event "mode → auto"; auto_apply force; }
do_seamless(){ sense_refresh; cfg_seamless; save_mode seamless; log_event "mode → seamless"; }   # location-aware default
do_phone()   { cfg_phone_first force; log_event "manual: grab iPhone now"; }   # one-shot nudge onto the hotspot

# ---- single-flight mode application (last-writer-wins; fixes the dashboard race) ----
# apply_one runs a mode's network config WITHOUT the lock (used by the worker & scheduler).
apply_one() {
  case "$1" in
    observe)  do_observe ;;
    seamless) do_seamless ;;
    auto)     do_auto ;;
    failover) do_failover ;;
    anchor)   do_anchor ;;
    solo)     do_solo ;;
    ladder)   do_ladder ;;
    phone)    do_phone ;;     # one-shot nudge; does not persist as the base mode
    *) return 1 ;;
  esac
}
APPLYFN=apply_one   # indirection so selftest can stub the applier
converge() {        # drain $DESIRED through $APPLYFN until it stops changing (assumes lock held)
  local applied="" want
  while :; do
    want=$(cat "$DESIRED" 2>/dev/null)
    { [ -z "$want" ] || [ "$want" = "$applied" ]; } && break
    "$APPLYFN" "$want"; applied="$want"
  done
}
apply_mode() {  # $1=mode. Serialize via an atomic mkdir lock; always converge to the LATEST intent.
  case "$1" in observe|seamless|auto|failover|anchor|solo|ladder|phone) ;; *) return 1;; esac
  printf '%s\n' "$1" > "$DESIRED"
  local g=0; [ -f "$GENFILE" ] && g=$(cat "$GENFILE" 2>/dev/null); case "$g" in ''|*[!0-9]*) g=0;; esac
  echo $((g+1)) > "$GENFILE"
  # become the worker, or bail: whoever holds the lock will pick up our freshly-written DESIRED.
  mkdir "$LOCKD" 2>/dev/null || return 0
  : > "$LOCK"                       # back-compat marker (older json/UI may glance at it)
  converge
  rm -f "$LOCK"; rmdir "$LOCKD" 2>/dev/null
}

# ---- usage metering (cycle-aware) ------------------------------------------
read_iface_bytes() { netstat -ibn 2>/dev/null | awk -v i="$1" '$1==i && $3 ~ /Link/ {print $7+$10; exit}'; }

# Per-link billing cycle math: each link resets on its own day-of-month.
cycle_start() {  # reset_day -> YYYY-MM-DD of the current cycle's start
  local rd=$1 td; td=$((10#$(date +%d))); case "$rd" in ''|*[!0-9]*) rd=1;; esac
  if [ "$td" -ge "$rd" ]; then date -v1d -v${rd}d +%Y-%m-%d
  else date -v1d -v-1m -v${rd}d +%Y-%m-%d; fi
}
cycle_next() {   # reset_day -> YYYY-MM-DD of the next reset (cycle end)
  local rd=$1 td; td=$((10#$(date +%d))); case "$rd" in ''|*[!0-9]*) rd=1;; esac
  if [ "$td" -ge "$rd" ]; then date -v1d -v+1m -v${rd}d +%Y-%m-%d
  else date -v1d -v${rd}d +%Y-%m-%d; fi
}
cycle_dates() {  # back-compat: sets CSTART CNEXT for the phone cycle (+ CKEY for legacy callers)
  CSTART=$(cycle_start "$PHONE_RESET_DAY"); CNEXT=$(cycle_next "$PHONE_RESET_DAY"); CKEY=${CSTART%-*}
}
epoch() { date -j -f "%Y-%m-%d" "$1" +%s 2>/dev/null; }

# ---- link identity & per-link config ---------------------------------------
link_cap()   { case "$1" in phone) echo "${PHONE_CAP_GB:-0}";; starlink) echo "${STARLINK_CAP_GB:-0}";; *) echo 0;; esac; }
link_reset() { case "$1" in phone) echo "${PHONE_RESET_DAY:-1}";; starlink) echo "${STARLINK_RESET_DAY:-1}";; *) echo "${RESET_DAY:-1}";; esac; }
link_cyclekey() { cycle_start "$(link_reset "$1")"; }   # the cycle-start date is the per-link cycle key
link_label() { case "$1" in phone) echo "📱 iPhone";; starlink) echo "🛰 Starlink";; free) echo "🆓 free Wi-Fi";; *) echo "$1";; esac; }
classify_link() {  # gw [ssid] -> phone | starlink | free  (any non-metered network is 'free')
  local gw="$1" ssid="${2:-}"
  [ -n "$gw" ] && [ "$gw" = "$PHONE_GW" ] && { echo phone; return; }
  { [ -n "$gw" ] && [ "$gw" = "$STARLINK_GW" ]; } && { echo starlink; return; }
  { [ -n "$ssid" ] && [ "$ssid" = "$STARLINK_SSID" ]; } && { echo starlink; return; }
  echo free
}

# ============================================================================
# Location & phone-presence sensing — "where am I?" + "is my phone here?"
# Cheap IO wrappers feed two PURE decision functions (testable in selftest).
# This is what lets netmode enforce "never Starlink at home" and stop clinging
# to a dead hotspot — without the human being the router.
# ============================================================================

# --- IO wrappers (the "all the ways") ---------------------------------------
# One Wi-Fi scan -> the SET of SSIDs currently in range (names sit at a fixed
# 12-space indent, line ends in ':'; covers both the joined net and neighbors).
scan_ssids() {
  system_profiler SPAirPortDataType 2>/dev/null | awk '
    { n=match($0,/[^ ]/); if(n==0) next; ind=n-1
      if (ind==12 && $0 ~ /:[ \t]*$/){ s=$0; sub(/^[ \t]+/,"",s); sub(/:[ \t]*$/,"",s); if(s!="") print s } }
  ' | sort -u
}

# Bluetooth proximity: the iPhone shows an RSSI reading when it's in BT range
# (~10m = same room/cabin) even while "Not Connected". Strongest "phone walked
# off" signal. ~1-2s, so we call it only as a tiebreaker. 0=in range,1=not.
bt_iphone_present() {
  local want="${PHONE_BT_NAME:-$PHONE_SSID}"
  system_profiler SPBluetoothDataType 2>/dev/null | awk -v want="$want" '
    { n=match($0,/[^ ]/); if(n==0) next; ind=n-1
      if (ind>=8 && ind<=10 && $0 ~ /:[ \t]*$/){ d=$0; sub(/^[ \t]+/,"",d); sub(/:[ \t]*$/,"",d); cur=d; next }
      if (cur==want && $0 ~ /RSSI:/){ found=1 } }
    END{ exit found?0:1 }'
}

# count of learned home SSIDs that are visible in the given scan (stdin = scan)
fp_overlap() {
  [ -s "$HOME_FP" ] || { echo 0; return; }
  awk 'NR==FNR{ if($0!="") fp[$0]=1; next } { if($0 in fp) c++ } END{ print c+0 }' "$HOME_FP" -
}

# learn/refresh the home fingerprint from a confident-home scan (stdin = scan).
# Excludes the phone hotspot SSID (it travels with you, so it's not a home anchor).
fp_learn() {
  local tmp="$HOME_FP.tmp"
  # exclude the phone hotspot (travels with you), Starlink, and ubiquitous public/carrier nets
  # (they appear everywhere -> would falsely match "home" elsewhere). Cap size so it can't grow unbounded.
  { [ -s "$HOME_FP" ] && cat "$HOME_FP"; cat; } 2>/dev/null \
    | grep -vxF "$PHONE_SSID" | grep -vxF "$STARLINK_SSID" \
    | grep -Eiv "${UBIQUITOUS_SSIDS:-^$}" \
    | grep . | sort -u | head -n "${HOME_FP_MAX:-200}" > "$tmp" 2>/dev/null
  [ -s "$tmp" ] && mv "$tmp" "$HOME_FP" || rm -f "$tmp"
}

# --- pure decisions (no IO; unit-tested) ------------------------------------
# phone_decide usb ssid_visible on_phone_wifi bt_present -> tethered|near|gone
phone_decide() {
  local usb="$1" sv="$2" ow="$3" bt="$4"
  { [ "$usb" = 1 ] || [ "$ow" = 1 ]; } && { echo tethered; return; }   # actively carrying phone data
  { [ "$sv" = 1 ] || [ "$bt" = 1 ]; } && { echo near; return; }        # phone here, hotspot reachable/wakeable
  echo gone
}
# location_decide starlink_visible overlap have_fingerprint scan_count -> home|away|unknown
location_decide() {
  local sv="$1" ov="$2" hf="$3" cnt="$4"; case "$cnt" in ''|*[!0-9]*) cnt=0;; esac; case "$ov" in ''|*[!0-9]*) ov=0;; esac
  [ "$cnt" = 0 ] && { echo unknown; return; }                          # Wi-Fi off / nothing in range -> can't sense
  [ "$sv" = 1 ] && { echo home; return; }                             # Starlink (the TV's link) in range = the apartment
  { [ "$hf" = 1 ] && [ "$ov" -ge "${HOME_MIN_OVERLAP:-2}" ]; } && { echo home; return; }
  # degraded-scan guard: we HAVE a home fingerprint, yet this scan matched none of it and saw almost
  # nothing. A real new place shows several APs; a near-empty zero-overlap scan is likelier a blocked/
  # redacted scan (e.g. macOS Location Services off) -> don't conclude "away" (that re-permits Starlink); hold.
  { [ "$hf" = 1 ] && [ "$ov" = 0 ] && [ "$cnt" -lt "${HOME_MIN_OVERLAP:-2}" ]; } && { echo unknown; return; }
  echo away
}

# --- live sensing (IO + debounce + manual override) -------------------------
phone_present() {
  local usb=0 sv=0 ow=0 bt=0
  usb_up && usb=1
  ssid_visible "$PHONE_SSID" && sv=1
  on_phone_wifi && ow=1
  # BT is slow; only consult it when the cheap signals say the phone isn't obviously here
  if [ "$usb" = 0 ] && [ "$sv" = 0 ] && [ "$ow" = 0 ]; then bt_iphone_present && bt=1; fi
  phone_decide "$usb" "$sv" "$ow" "$bt"
}

location() {  # debounced home|away|unknown, honoring an unexpired manual pin
  if [ -f "$LOC_OVERRIDE" ]; then
    local ov exp; read -r ov exp < "$LOC_OVERRIDE"
    case "$exp" in ''|*[!0-9]*) exp=0;; esac
    [ "$(date +%s)" -lt "$exp" ] && { echo "$ov"; return; }
  fi
  local sv=0 scan cnt overlap hf=0 raw
  ssid_visible "$STARLINK_SSID" && sv=1
  scan=$(scan_ssids); cnt=$(printf '%s\n' "$scan" | grep -c .)
  [ -s "$HOME_FP" ] && hf=1
  overlap=$(printf '%s\n' "$scan" | fp_overlap)
  raw=$(location_decide "$sv" "$overlap" "$hf" "$cnt")
  [ "$sv" = 1 ] && printf '%s\n' "$scan" | fp_learn      # confidently home -> learn the ambient fingerprint
  # strong-away: a healthy foreign scan with no Starlink and zero home-overlap is unambiguous -> leave home
  # in ONE sample (no home-Starlink can be present to wrongly grab, so the 3-sample wait would only strand us).
  local need=""
  { [ "$raw" = away ] && [ "$sv" = 0 ] && [ "$overlap" = 0 ] && [ "$cnt" -ge "${STRONG_AWAY_MIN:-6}" ]; } && need=1
  location_commit "$raw" "$need"
}

location_commit() {  # 2-sample debounce so one bad scan can't flip the policy; optional $2 forces the sample count
  local raw="$1" need_override="$2" committed="" pending="" pc=0
  [ -f "$LOCSTATE" ] && read -r committed pending pc < "$LOCSTATE"
  case "$pc" in ''|*[!0-9]*) pc=0;; esac
  [ -z "$committed" ] && committed="$raw"
  if [ "$raw" = unknown ]; then echo "$committed"; printf '%s %s %s\n' "$committed" "" 0 > "$LOCSTATE"; return; fi
  # asymmetric hysteresis: abandoning "home" (which re-permits the TV's Starlink) demands more
  # consecutive confirmations than coming home, so a transient bad scan can't quietly flip us off the rule.
  local need=2; { [ "$committed" = home ] && [ "$raw" = away ]; } && need=${LEAVE_HOME_SAMPLES:-3}
  # caller may shrink that wait when the evidence is unambiguous (strong-away: healthy foreign scan, no Starlink)
  case "$need_override" in ''|*[!0-9]*) ;; *) need="$need_override";; esac
  if [ "$raw" = "$committed" ]; then pending=""; pc=0
  else
    if [ "$raw" = "$pending" ]; then pc=$((pc+1)); else pending="$raw"; pc=1; fi
    # check the threshold regardless of which branch advanced the counter, so need=1 flips on the FIRST sample
    [ "$pc" -ge "$need" ] && { committed="$raw"; pending=""; pc=0; log_event "location → $committed"; }
  fi
  printf '%s %s %s\n' "$committed" "$pending" "$pc" > "$LOCSTATE"
  echo "$committed"
}

loc_set() {  # manual pin: loc_set home|away  (expires after LOC_OVERRIDE_HOURS)
  case "$1" in home|away) ;; *) echo "usage: netmode here|out"; return 1;; esac
  local exp; exp=$(( $(date +%s) + ${LOC_OVERRIDE_HOURS:-4}*3600 ))
  printf '%s %s\n' "$1" "$exp" > "$LOC_OVERRIDE"
  log_event "manual location pin: $1 (${LOC_OVERRIDE_HOURS:-4}h)"
  echo "📍 pinned location = $1 for ${LOC_OVERRIDE_HOURS:-4}h"; apply_mode "$(get_mode)"
}
loc_clear() { rm -f "$LOC_OVERRIDE"; log_event "manual location pin cleared"; echo "📍 location pin cleared — sensing resumed"; }

# Fast cached readers (system_profiler is slow; the dashboard polls json often). tick() refreshes
# $SENSE; these read it so json never shells out to system_profiler on the hot path.
sense_field() { [ -f "$SENSE" ] || { echo ""; return; }; local l p s; IFS=$'\t' read -r l p s < "$SENSE"
  case "$1" in loc) echo "$l";; pres) echo "$p";; star) echo "$s";; esac; }
location_cached() {  # honor an unexpired pin, else the last sensed (debounced) location
  if [ -f "$LOC_OVERRIDE" ]; then local ov exp; read -r ov exp < "$LOC_OVERRIDE"; case "$exp" in ''|*[!0-9]*) exp=0;; esac
    [ "$(date +%s)" -lt "$exp" ] && { echo "$ov"; return; }; fi
  local l; l=$(sense_field loc); echo "${l:-unknown}"; }
presence_cached()  { local p; p=$(sense_field pres); echo "${p:-unknown}"; }
sense_refresh() {  # one set of live probes -> cache (called by tick + on network-change events)
  local l p s; l=$(location); p=$(phone_present); s=$(ssid_visible "$STARLINK_SSID" && echo true || echo false)
  printf '%s\t%s\t%s\n' "$l" "$p" "$s" > "$SENSE"
}

# ---- per-(link,cycle) usage store: usage.tsv lines "link<TAB>cyclekey<TAB>bytes" ----
usage_get() {  # link -> bytes used in its CURRENT cycle
  local link="$1" ck b=0 L K B; ck=$(link_cyclekey "$link")
  [ -f "$USAGE" ] && while IFS=$'\t' read -r L K B; do [ "$L" = "$link" ] && [ "$K" = "$ck" ] && b=$B; done < "$USAGE"
  case "$b" in ''|*[!0-9]*) b=0;; esac; echo "$b"
}
usage_set() {  # link bytes -> overwrite this link's current-cycle total (used by anchor + add)
  local link="$1" bytes="$2" ck seen=0 tmp="$USAGE.tmp" L K B; ck=$(link_cyclekey "$link")
  : > "$tmp"
  [ -f "$USAGE" ] && while IFS=$'\t' read -r L K B; do
    [ -z "$L" ] && continue
    if [ "$L" = "$link" ] && [ "$K" = "$ck" ]; then continue   # drop old row; rewritten below
    else printf '%s\t%s\t%s\n' "$L" "$K" "$B" >> "$tmp"; fi
  done < "$USAGE"
  printf '%s\t%s\t%s\n' "$link" "$ck" "$bytes" >> "$tmp"
  mv "$tmp" "$USAGE"
}
usage_add() {  # link delta -> add delta bytes to this link's current cycle
  local link="$1" delta="$2"; case "$delta" in ''|*[!0-9]*) return 0;; esac
  [ "$delta" -le 0 ] && return 0
  usage_set "$link" $(( $(usage_get "$link") + delta ))
}

sample() {
  # Per-interface, reset-aware metering across N networks. en8 = USB-tethered iPhone (always 'phone');
  # en0 carries phone-Wi-Fi, Starlink AND any other Wi-Fi — classified live by gateway/SSID into
  # phone | starlink | free. We track each interface's cumulative counter independently and NEVER drop an
  # interval on a network change (the old gw-equality rule discarded ~90% of continuous upload, e.g.
  # Backblaze, undercounting ~20x). At most one boundary interval is mislabeled — far better than losing it.
  local gw ssid cur0 cur8 last0 last8 fresh=0 d0=0 d8=0 link
  gw=$(route -n get default 2>/dev/null | awk '/gateway/{print $2; exit}')
  ssid=$(current_ssid 2>/dev/null)
  cur0=$(read_iface_bytes "$WIFI_IF"); cur8=$(read_iface_bytes "$USB_IF")
  case "$cur0" in ''|*[!0-9]*) cur0="";; esac
  case "$cur8" in ''|*[!0-9]*) cur8="";; esac
  last0=0; last8=0
  if [ -f "$STATE" ]; then read -r last0 last8 < "$STATE"; else fresh=1; fi
  case "$last0" in ''|*[!0-9]*) fresh=1; last0=0;; esac   # also migrates the legacy STATE format
  case "$last8" in ''|*[!0-9]*) fresh=1; last8=0;; esac
  # reset-aware: a counter going backwards = reboot / interface re-init -> count cur from zero, don't drop
  [ -n "$cur0" ] && { if [ "$cur0" -ge "$last0" ]; then d0=$((cur0-last0)); else d0=$cur0; fi; }
  [ -n "$cur8" ] && { if [ "$cur8" -ge "$last8" ]; then d8=$((cur8-last8)); else d8=$cur8; fi; }
  printf '%s %s\n' "${cur0:-$last0}" "${cur8:-$last8}" > "$STATE"
  [ "$fresh" = 1 ] && return 0   # first run after install/migration: just set the baseline, count nothing
  [ "$d8" -gt 0 ] && usage_add phone "$d8"          # USB is always the iPhone hotspot
  link=$(classify_link "$gw" "$ssid")               # what is Wi-Fi (en0) on right now?
  [ "$d0" -gt 0 ] && usage_add "$link" "$d0"
}

# back-compat shim: "phone_bytes starlink_bytes" for the few callers that still want the pair
usage_bytes() { echo "$(usage_get phone) $(usage_get starlink)"; }
gb()  { awk -v b="$1" 'BEGIN{printf "%.1f", b/1073741824}'; }
gbf() { awk -v b="$1" 'BEGIN{printf "%.3f", b/1073741824}'; }

# projection math for a given link -> sets CSTART CNEXT DOY DIC DLEFT PROJ DTOCAP (defaults to phone)
project() {
  local link="${1:-phone}" rd; rd=$(link_reset "$link")
  CSTART=$(cycle_start "$rd"); CNEXT=$(cycle_next "$rd")
  local now today cse cne; now=$(date +%s); today=$(epoch "$(date +%Y-%m-%d)")
  cse=$(epoch "$CSTART"); cne=$(epoch "$CNEXT")
  DIC=$(( (cne - cse) / 86400 ))
  DOY=$(( (today - cse) / 86400 + 1 ))
  DLEFT=$(( (cne - now + 86399) / 86400 ))
  local g cap; g=$(gbf "$(usage_get "$link")"); cap=$(link_cap "$link")
  PROJ=$(awk -v g="$g" -v d="$DOY" -v t="$DIC" 'BEGIN{ if(d<1)d=1; printf "%.0f", (g/d)*t }')
  PROJP="$PROJ"   # back-compat alias
  DTOCAP=$(awk -v g="$g" -v d="$DOY" -v c="$cap" 'BEGIN{ if(d<1)d=1; r=g/d; if(r<=0||c<=0){print "—"} else {x=(c-g)/r; if(x<0)x=0; printf "%.0f", x} }')
}

# ---- health (per-link reachability + latency + packet loss + quality score) -
ping_probe() {  # $1=source-ip. echo "avg_ms loss%"; "down 100" when unreachable/no source.
  local ip="$1"; [ -z "$ip" ] && { echo "down 100"; return; }
  local out loss lat
  out=$(ping -c3 -t2 -S "$ip" 1.1.1.1 2>/dev/null)
  loss=$(printf '%s\n' "$out" | sed -n 's/.* \([0-9][0-9.]*\)% packet loss.*/\1/p' | head -1)
  loss=${loss%%.*}; case "$loss" in ''|*[!0-9]*) loss=100;; esac
  lat=$(printf '%s\n' "$out" | awk -F'/' '/round-trip|min\/avg/{print $5; exit}')
  lat=${lat%%.*}; case "$lat" in ''|*[!0-9]*) lat="";; esac
  if [ "$loss" -ge 100 ] || [ -z "$lat" ]; then echo "down $loss"; else echo "$lat $loss"; fi
}

# pure, testable: latency(ms or "down") + loss(%) -> 0..100. loss hurts hard, latency only past 40ms.
link_score() {
  local lat="$1" loss="$2"
  [ "$lat" = down ] && { echo 0; return; }
  case "$lat" in ''|*[!0-9]*) echo 0; return;; esac
  case "$loss" in ''|*[!0-9]*) loss=0;; esac
  awk -v l="$lat" -v p="$loss" 'BEGIN{ s=100 - p*1.5 - (l>40 ? (l-40)*0.25 : 0)
    if(s<0)s=0; if(s>100)s=100; printf "%d", s }'
}

health_record() {  # writes "phonelat phoneloss starlat starloss" to $HEALTH + rolling $HEALTHTSV
  local pip sip pr sr pl ploss sl sloss
  # Phone: USB interface if tethered, else Wi-Fi when Wi-Fi is on the phone hotspot.
  if usb_up; then pip=$(ipconfig getifaddr "$USBIF" 2>/dev/null)
  elif on_phone_wifi; then pip=$(wifi_ip)
  else pip=""; fi
  # Starlink: only meaningful when Wi-Fi is actually on a non-phone (Starlink) network.
  if on_starlink; then sip=$(wifi_ip); else sip=""; fi
  pr=$(ping_probe "$pip"); sr=$(ping_probe "$sip")
  read -r pl ploss <<<"$pr"; read -r sl sloss <<<"$sr"
  printf '%s %s %s %s\n' "$pl" "$ploss" "$sl" "$sloss" > "$HEALTH"
  local ts; ts=$(date "+%Y-%m-%d %H:%M")
  printf '%s\t%s\t%s\t%s\t%s\n' "$ts" "$pl" "$ploss" "$sl" "$sloss" >> "$HEALTHTSV"
  tail -n 50 "$HEALTHTSV" > "$HEALTHTSV.tmp" 2>/dev/null && mv "$HEALTHTSV.tmp" "$HEALTHTSV"
}

# ---- events / notifications ------------------------------------------------
log_event() { local ts; ts=$(date "+%Y-%m-%d %H:%M"); printf '%s\t%s\n' "$ts" "$1" >> "$EVENTS"
  [ -f "$EVENTS" ] && { tail -n 60 "$EVENTS" > "$EVENTS.tmp" 2>/dev/null && mv "$EVENTS.tmp" "$EVENTS"; }; }
notify() { osascript -e "display notification \"$1\" with title \"🌐 netmode\" subtitle \"${2:-}\"" >/dev/null 2>&1; }

_nrank() { case "$1" in none)echo 0;; warn)echo 1;; crit)echo 2;; cap)echo 3;; *)echo 0;; esac; }
notify_check() {  # throttled cap-threshold notifications, per metered link (state lines: "link cyclekey level")
  local link cap used pct lvl ck prev pck L K V lbl tmp
  for link in phone starlink; do
    cap=$(link_cap "$link"); case "$cap" in ''|*[!0-9]*|0) continue;; esac
    used=$(usage_get "$link"); ck=$(link_cyclekey "$link")
    pct=$(awk -v g="$(gbf "$used")" -v c="$cap" 'BEGIN{printf "%.0f",(g/c)*100}')
    lvl=none
    [ "$pct" -ge "$WARN_PCT" ] && lvl=warn
    [ "$pct" -ge "$CRIT_PCT" ] && lvl=crit
    [ "$pct" -ge 100 ] && lvl=cap
    prev=none; pck=""
    [ -f "$NOTIFY" ] && while read -r L K V; do [ "$L" = "$link" ] && { pck=$K; prev=$V; }; done < "$NOTIFY"
    [ "$pck" != "$ck" ] && prev=none
    if [ "$(_nrank "$lvl")" -gt "$(_nrank "$prev")" ]; then
      lbl=$(link_label "$link")
      case "$lvl" in
        warn) notify "$lbl at ${pct}% of ${cap}GB" "metered link" ;;
        crit) notify "$lbl at ${pct}% — nearly out" "approaching cap" ;;
        cap)  notify "$lbl cap reached (${cap}GB)" "$([ "$link" = phone ] && echo "Starlink takes over now" || echo "throttled for the cycle")" ;;
      esac
      log_event "alert: $link ${pct}% (${lvl})"
      tmp="$NOTIFY.tmp"; : > "$tmp"
      [ -f "$NOTIFY" ] && while read -r L K V; do [ "$L" = "$link" ] || printf '%s %s %s\n' "$L" "$K" "$V" >> "$tmp"; done < "$NOTIFY"
      printf '%s %s %s\n' "$link" "$ck" "$lvl" >> "$tmp"; mv "$tmp" "$NOTIFY"
    fi
  done
}

# ---- auto mode policy ------------------------------------------------------
over_cap_calc()  { awk -v b="$1" -v c="${2:-$PHONE_CAP_GB}" 'BEGIN{exit !((b/1073741824)>=c)}'; }   # pure: bytes cap_gb
over_cap_phone() { over_cap_calc "$(usage_get phone)" "$PHONE_CAP_GB"; }
auto_want()      { if [ "$AUTO_SWITCH" = 1 ] && over_cap_phone; then echo starlink; else echo phone; fi; }
background_switching_enabled() { [ "${BACKGROUND_SWITCHING:-0}" = 1 ]; }

auto_apply() {  # $1=force (kept for call-site compat; cascade now self-heals every tick regardless)
  local want cur=""; want=$(auto_want)
  [ -f "$AUTOSTATE" ] && cur=$(cat "$AUTOSTATE")
  # Always re-run the cascade (it self-heals Wi-Fi homing each tick); only notify/log on a real change.
  if [ "$want" = starlink ]; then
    cfg_anchor
    [ "$want" != "$cur" ] && { notify "iPhone ${PHONE_CAP_GB}GB used — switched to Starlink" "auto mode"; log_event "auto → Starlink (phone cap hit)"; }
  else
    cfg_phone_first
    [ "$want" != "$cur" ] && { notify "On iPhone — burning hotspot first" "auto mode (${PHONE_CAP_GB}GB before Starlink)"; log_event "auto → iPhone (burn ${PHONE_CAP_GB}GB first)"; }
  fi
  echo "$want" > "$AUTOSTATE"
}

# ---- reliability: recover when the ACTIVE link has no internet --------------
auto_recover() {
  [ "$AUTO_RECOVER" = 1 ] || return 0
  local m; m=$(get_mode); case "$m" in failover|auto|seamless) ;; *) return 0;; esac
  # seamless at home is phone-only by design — never auto-flip it onto Starlink (the TV's link).
  [ "$m" = seamless ] && [ "$(location_cached)" = home ] && return 0
  local pl ploss sl sloss; read -r pl ploss sl sloss < "$HEALTH" 2>/dev/null
  local using; using=$(live_path)
  local pscore sscore; pscore=$(link_score "${pl:-down}" "${ploss:-100}"); sscore=$(link_score "${sl:-down}" "${sloss:-100}")
  # The ACTIVE link is bad (down or sustained poor quality)? Flip to the other and let next tick measure it.
  # Quality of the *other* link can't be probed without switching, so we judge the active link only.
  local dead=""
  case "$using" in
    phone)    [ "$pscore" -lt 25 ] && dead=phone ;;
    starlink) [ "$sscore" -lt 25 ] && dead=star ;;
  esac
  local c=0; [ -f "$DEADCNT" ] && c=$(cat "$DEADCNT"); case "$c" in ''|*[!0-9]*) c=0;; esac
  if [ -n "$dead" ]; then c=$((c+1)); echo "$c" > "$DEADCNT"
    if [ "$c" -ge 2 ]; then   # ~10 min of a bad active link -> flip
      if [ "$dead" = phone ]; then cfg_anchor; notify "iPhone link is bad — trying Starlink" "auto-recover"; log_event "auto-recover → Starlink (phone score ${pscore})"
      else cfg_phone_first; notify "Starlink is bad — trying iPhone" "auto-recover"; log_event "auto-recover → iPhone (starlink score ${sscore})"; fi
      echo 0 > "$DEADCNT"
    fi
  else echo 0 > "$DEADCNT"; fi
}

# ---- client recycle on network switch --------------------------------------
# The link can be perfectly healthy yet long-lived processes (the limen heartbeat
# daemon, any `claude` session) keep TCP keep-alive sockets + cached DNS bound to
# the OLD network. macOS does not tear those down on a Wi-Fi switch, so every
# request rides a dead socket -> "API unavailable" until the OS times it out
# (~1-2 min). Fired from tick(): when the default gateway changes, flush DNS and
# kickstart the registered daemons so they rebuild their connection pools at once.
LAST_GW="$DIR/last_gw"
recycle_clients() {
  [ "$RECYCLE_CLIENTS" = 1 ] || return 0
  local gw prev; gw=$(route -n get default 2>/dev/null | awk '/gateway/{print $2;exit}')
  [ -n "$gw" ] || return 0                       # no default route yet — nothing to recycle onto
  prev=""; [ -f "$LAST_GW" ] && prev=$(cat "$LAST_GW" 2>/dev/null)
  printf '%s\n' "$gw" > "$LAST_GW"
  [ -z "$prev" ] && return 0                      # first observation — just record the baseline
  [ "$gw" = "$prev" ] && return 0                 # same network — do NOT kick on every periodic tick
  dscacheutil -flushcache 2>/dev/null || true     # best-effort (no-op without root); IP stays valid anyway
  local lbl uid; uid=$(id -u)
  for lbl in $RECYCLE_LABELS; do
    launchctl list 2>/dev/null | grep -q "$lbl" && launchctl kickstart -k "gui/$uid/$lbl" 2>/dev/null || true
  done
  log_event "recycle → gateway $prev → $gw; kicked: $RECYCLE_LABELS"
}

# ---- ladder invariant ------------------------------------------------------
enforce() {
  # ladder = always phone-first regardless of cap (USB → phone-WiFi → Starlink). Same cascade as auto's
  # under-cap path, which try-joins the phone (reliable) instead of the passive ssid_visible scan (can't
  # see the iPhone hotspot). auto adds the cap-driven switch on top; ladder never gives up the phone.
  case "$(get_mode)" in
    ladder) cfg_phone_first ;;
  esac
}

# ---- schedules: time-of-day rules ("dynamic, not black-and-white") ----------
# schedule.tsv lines: "HHMM HHMM mode" (wrap-around allowed, e.g. "2300 0700 anchor").
# Empty/missing file = no rules = unchanged behavior.
schedule_match() {  # $1=HHMM -> echoes the matching mode, or nothing
  [ -f "$SCHEDULE" ] || return 0
  local now s e mode; now=$((10#${1:-0}))
  while read -r s e mode; do
    case "$s" in ''|\#*|*[!0-9]*) continue;; esac
    case "$e" in ''|*[!0-9]*) continue;; esac
    case "$mode" in auto|failover|anchor|solo|ladder) ;; *) continue;; esac
    s=$((10#$s)); e=$((10#$e))
    if [ "$s" -le "$e" ]; then
      [ "$now" -ge "$s" ] && [ "$now" -lt "$e" ] && { echo "$mode"; return 0; }
    else
      { [ "$now" -ge "$s" ] || [ "$now" -lt "$e" ]; } && { echo "$mode"; return 0; }
    fi
  done < "$SCHEDULE"
  return 0
}
in_anchor_window() {  # $1=HHMM -> exit 0 if inside the overnight anchor window (wrap-around aware); empty/absent = never
  [ -s "$ANCHORWIN" ] || return 1
  local now s e; now=$((10#${1:-0}))
  read -r s e < "$ANCHORWIN" || return 1
  case "$s" in ''|*[!0-9]*) return 1;; esac
  case "$e" in ''|*[!0-9]*) return 1;; esac
  s=$((10#$s)); e=$((10#$e))
  if [ "$s" -le "$e" ]; then [ "$now" -ge "$s" ] && [ "$now" -lt "$e" ]
  else { [ "$now" -ge "$s" ] || [ "$now" -lt "$e" ]; }; fi
}
anchor_window() {  # CLI: `overnight 0100 0700` (set) | `overnight off` (clear) | `overnight` (show)
  case "${1:-}" in
    ''|show) if [ -s "$ANCHORWIN" ]; then local s e; read -r s e < "$ANCHORWIN"; echo "overnight anchor: Starlink ${s}–${e}$(in_anchor_window "$(date +%H%M)" && echo " (active now)")"; else echo "overnight anchor: off"; fi; return 0;;
    off|none|0) : > "$ANCHORWIN"; rm -f "$_ANCHORSAID" "$_ANCHORFAIL" 2>/dev/null; log_event "overnight anchor → off"; echo "✅ overnight anchor off — home is iPhone-only around the clock"; return 0;;
  esac
  local s="$1" e="$2"
  case "$s" in *[!0-9]*|'') echo "usage: netmode overnight HHMM HHMM | off"; return 1;; esac
  case "$e" in *[!0-9]*|'') echo "usage: netmode overnight HHMM HHMM | off"; return 1;; esac
  { [ "${#s}" -ne 4 ] || [ "${#e}" -ne 4 ] || [ "$((10#$s))" -ge 2400 ] || [ "$((10#$e))" -ge 2400 ]; } && { echo "usage: HHMM HHMM, e.g. netmode overnight 0100 0700"; return 1; }
  printf '%s %s\n' "$s" "$e" > "$ANCHORWIN"; rm -f "$_ANCHORSAID" "$_ANCHORFAIL" 2>/dev/null
  log_event "overnight anchor → ${s}-${e}"
  echo "✅ overnight anchor: Starlink ${s}–${e} (home only) — backups ride Starlink, not the phone cap"
}
set_schedule() {  # reads rules on stdin ("HHMM HHMM mode" or "HHMM-HHMM mode"); validates & writes
  local tmp="$SCHEDULE.tmp" n=0 line s e mode
  : > "$tmp"
  while IFS= read -r line; do
    set -- $(printf '%s' "$line" | tr ',-' '  '); s="$1"; e="$2"; mode="$3"
    case "$s" in ''|*[!0-9]*) continue;; esac
    case "$e" in ''|*[!0-9]*) continue;; esac
    [ "${#s}" -le 4 ] && [ "${#e}" -le 4 ] || continue
    case "$mode" in auto|failover|anchor|solo|ladder) ;; *) continue;; esac
    printf '%s %s %s\n' "$s" "$e" "$mode" >> "$tmp"; n=$((n+1))
  done
  mv "$tmp" "$SCHEDULE"; log_event "schedule: $n rule(s)"
  echo "✅ $n schedule rule(s) saved"
}
schedule_tick() {  # apply schedule only at window edges; manual changes stick within a window
  local nowhhmm cur prevwin; nowhhmm=$(date +%H%M)
  cur=$(schedule_match "$nowhhmm")
  prevwin=""; [ -f "$SCHEDWIN" ] && prevwin=$(cat "$SCHEDWIN")
  [ "$cur" = "$prevwin" ] && return 0          # no edge -> leave the active mode alone
  printf '%s\n' "$cur" > "$SCHEDWIN"
  if [ -n "$cur" ]; then
    [ -z "$prevwin" ] && get_mode > "$DIR/base_mode"   # entering schedule control -> remember base
    [ "$(get_mode)" != "$cur" ] && { apply_one "$cur"; log_event "schedule → $cur ($nowhhmm)"; }
  else
    local base=auto; [ -f "$DIR/base_mode" ] && base=$(cat "$DIR/base_mode")
    [ "$(get_mode)" != "$base" ] && { apply_one "$base"; log_event "schedule end → $base"; }
    rm -f "$DIR/base_mode"
  fi
}

# ---- the 5-minute tick (launchd) -------------------------------------------
tick() {
  recycle_clients                      # net switched? drop stale sockets before anything else measures
  sample
  health_record
  sense_refresh                        # refresh location/presence cache for the dashboard + the policy below
  if background_switching_enabled; then
    schedule_tick
    case "$(get_mode)" in
      seamless) cfg_seamless ;;          # location-aware: phone-only at home, full cascade away
      auto) auto_apply ;;
      failover|anchor) on_starlink || ensure_starlink_standby >/dev/null 2>&1 ;;
      ladder) enforce ;;
      solo) on_starlink && wifi_off ;;   # never Starlink: if Wi-Fi drifted onto it, cut it (phone-Wi-Fi is left alone)
    esac
    auto_recover
  fi
  notify_check
  history_snapshot
}

history_snapshot() {  # upsert today's cumulative usage
  cycle_dates; read -r pb ob < <(usage_bytes)
  local today pg og; today=$(date +%Y-%m-%d); pg=$(gb "$pb"); og=$(gb "$ob")
  local tmp="$HISTORY.tmp"; : > "$tmp"
  [ -f "$HISTORY" ] && grep -v "^$today	" "$HISTORY" >> "$tmp" 2>/dev/null
  printf '%s\t%s\t%s\n' "$today" "$pg" "$og" >> "$tmp"
  tail -n 90 "$tmp" > "$HISTORY"; rm -f "$tmp"
}

# ---- presentation ----------------------------------------------------------
live_path() {  # phone | starlink | free | offline — single source of truth via classify_link
  local gw ifc; gw=$(route -n get default 2>/dev/null | awk '/gateway/{print $2;exit}')
  ifc=$(route -n get default 2>/dev/null | awk '/interface/{print $2;exit}')
  [ -z "$ifc" ] && { echo "offline"; return; }
  # delegate to the same classifier metering uses, so a foreign/café gateway reports 'free'
  # (not a bogus 'starlink'). auto_recover branches only on phone/starlink, so 'free' makes it
  # correctly inert on foreign Wi-Fi — link selection stays with the seamless-away cascade.
  classify_link "$gw" "$(current_ssid 2>/dev/null)"
}
wifi_state_str() {
  local pwr ip; pwr=$(networksetup -getairportpower "$WIFI" 2>/dev/null | awk '{print $NF}'); ip=$(wifi_ip)
  [ "$pwr" != On ] && { echo "off"; return; }
  [ -z "$ip" ] && { echo "on, no IP"; return; }
  on_phone_wifi && { echo "⚠ on PHONE hotspot"; return; }
  echo "Starlink standby"
}
phone_state_str() {  # honest phone-link state: credits USB cable OR the Wi-Fi hotspot, not USB alone
  if usb_up; then echo "via USB cable ($(ipconfig getifaddr "$USBIF" 2>/dev/null||echo "?"))"
  elif on_phone_wifi; then echo "via Wi-Fi hotspot ($(wifi_ip 2>/dev/null||echo "?"))"
  else echo "down"; fi
}

# one plain-English sentence: what the system is doing and what happens next
plan_line() {
  cycle_dates
  local m using; m=$(get_mode); using=$(live_path)
  case "$m" in
    observe)
      echo "Observe-only — metering and status update, but background automation will not switch networks. Use an explicit mode command to move links."
      return;;
    seamless)
      local loc pres; loc=$(location_cached); pres=$(presence_cached)
      case "$loc" in
        home)
          if in_anchor_window "$(date +%H%M)"; then local _as _ae; [ -s "$ANCHORWIN" ] && read -r _as _ae < "$ANCHORWIN"; echo "🌙 Home, overnight anchor (${_as}–${_ae}) — on Starlink on purpose so backups don't burn the phone cap. Back to iPhone-only when the window ends. \`netmode overnight off\` to disable."
          elif [ "$using" = phone ]; then echo "🏠 Home — on the iPhone, Starlink left for the TV. Walk off with the phone and it never grabs Starlink; it just waits and reconnects when you're back."
          elif [ "$pres" = gone ]; then echo "🏠 Home, phone has left — holding offline on purpose (Starlink is the TV's). Bring the phone back, or run \`netmode out\` to allow Starlink."
          else echo "🏠 Home — getting onto the iPhone hotspot; Starlink stays reserved for the TV."; fi ;;
        away)  echo "🚶 Out of the apartment — burning the iPhone first, falling to Starlink only if the phone's capped or gone. (On ${using}.)" ;;
        *)     echo "📍 Location not sensed yet (Wi-Fi off?) — acting like auto: iPhone first, Starlink as backup." ;;
      esac
      return;;
    solo)     if on_starlink; then echo "Solo (only the iPhone, never Starlink) — Wi-Fi is on Starlink right now; next tick cuts it."
              else echo "Solo: only the iPhone, Starlink never used. Phone via cable or its Wi-Fi hotspot; if the phone is unreachable you go offline (by design)."; fi; return;;
    anchor)   echo "Starlink-first to spare the phone — currently on ${using}. Switch to 'auto' to burn the hotspot first."; return;;
    failover) if usb_up; then echo "On the iPhone via cable. The instant you unplug it jumps to Starlink."
              else echo "On Starlink. Plug in the cable to use the iPhone."; fi; return;;
  esac
  # auto / ladder = phone-first
  if [ "$m" = auto ] && [ "$(auto_want)" = starlink ]; then
    echo "iPhone cap reached for this cycle — riding Starlink until it resets ${CNEXT}, then back to the iPhone automatically."; return
  fi
  case "$using" in
    phone)
      if usb_up; then echo "Burning iPhone data over the cable. Unplug and it stays on the iPhone Wi-Fi hotspot; only if the phone actually leaves does it drop to Starlink."
      else echo "Burning iPhone data over its Wi-Fi hotspot (no cable needed). If the phone leaves, it falls back to Starlink."; fi ;;
    starlink)
      echo "On Starlink because the iPhone hotspot isn't reachable right now. Plug in USB or run \`netmode phone\` to switch back instantly — otherwise it re-checks about every $((PROBE_EVERY*5)) min." ;;
    *)
      echo "Offline — trying the iPhone first, then Starlink." ;;
  esac
}

report_link() {  # one metered link, its OWN cycle/cap/projection
  local link="$1"; project "$link"
  local ug cap pct; ug=$(gb "$(usage_get "$link")"); cap=$(link_cap "$link")
  pct=$(awk -v g="$ug" -v c="$cap" 'BEGIN{if(c<=0){print 0}else{x=(g/c)*100; if(x>100)x=100; printf "%.0f",x}}')
  printf '  %-11s %s / %s GB (%s%%)  ·  resets %s (%sd left)\n' "$(link_label "$link")" "$ug" "$cap" "$pct" "$CNEXT" "$DLEFT"
  printf '  %-11s projected ~%s GB · cap in ~%s d at this rate\n' "" "$PROJ" "$DTOCAP"
}
report() {
  echo "📊 Usage this cycle  (each link resets on its OWN day)"
  echo "──────────────────────────────────────────────"
  report_link phone
  report_link starlink
  local fb; fb=$(usage_get free); case "$fb" in ''|*[!0-9]*) fb=0;; esac
  [ "$fb" -gt 0 ] && echo "  🆓 free Wi-Fi $(gb "$fb") GB this month (uncapped — not billed)"
  echo "──────────────────────────────────────────────"
}

status() {
  local m; m=$(get_mode)
  echo "┌─ netmode ─────────────────────────────────"
  echo "│ mode  : $m$( [ "$m" = auto ] && echo " (effective: $(cat "$AUTOSTATE" 2>/dev/null||echo phone))" )"
  echo "│ bg    : $(background_switching_enabled && echo switching || echo observe-only)"
  echo "│ using : $(live_path)"
  echo "│ phone : $(phone_state_str)   wifi: $(wifi_state_str)"
  echo "└───────────────────────────────────────────"
  echo "▶ Next move: $(plan_line)"
  echo; report
}

# ---- Starlink dish gRPC poller (READ-ONLY diagnostic; never switches links) -----------------
# The dish exposes a gRPC reflection API at 192.168.100.1:9200. Reachable only when the computer
# is on the Starlink LAN (i.e. away, on Starlink). On the iPhone hotspot it's silent — by design
# we cheap-check reachability first so grpcurl never hangs, and never call grpcurl on the hot
# json/doctor path (those read $DISHCACHE only).
dish_reachable() {  # exit 0 only if the dish LAN answers right now (cheap, ~1s max)
  nc -z -G1 "$DISH_GW" "$DISH_GPORT" >/dev/null 2>&1 && return 0
  ping -c1 -t1 "$DISH_GW" >/dev/null 2>&1
}
dish_fetch() {  # live poll -> raw grpcurl JSON on stdout (also cached). rc2=no grpcurl, rc3=unreachable
  command -v grpcurl >/dev/null 2>&1 || { echo "grpcurl not installed — run: brew install grpcurl"; return 2; }
  dish_reachable || { echo "dish unreachable (not on the Starlink LAN — connect to Starlink to read it)"; return 3; }
  local out; out=$(grpcurl -plaintext -max-time 4 -d '{"get_status":{}}' "$DISH_GW:$DISH_GPORT" SpaceX.API.Device.Device/Handle 2>/dev/null) || { echo "dish query failed"; return 4; }
  [ -n "$out" ] || { echo "dish returned no data"; return 4; }
  printf '%s\n' "$out" > "$DISHCACHE"
  printf '%s\n' "$out"
}
dish_parse() {  # PURE: grpcurl JSON on stdin -> flat "key=value" lines (missing -> ?). No network.
  # NB: python3 -c (NOT `python3 - <<heredoc`) so stdin stays the JSON data, not the program.
  python3 -c '
import sys, json
try: d = json.load(sys.stdin)
except Exception: print("error=unparseable"); sys.exit(0)
s = d.get("dishGetStatus", d) or {}
def g(o,*ks):
    for k in ks:
        if isinstance(o,dict) and k in o and o[k] is not None: o=o[k]
        else: return "?"
    return o
def mbps(v):
    try: return "%.1f" % (float(v)*8/1e6)
    except Exception: return "?"
def pct(v):
    try: return "%.2f" % (float(v)*100)
    except Exception: return "?"
up = g(s,"deviceState","uptimeS")
print("state=%s" % ("online" if up!="?" else (g(s,"state") if g(s,"state")!="?" else "unknown")))
print("uptime_s=%s" % up)
print("obstruction_pct=%s" % pct(g(s,"obstructionStats","fractionObstructed")))
ping = g(s,"popPingLatencyMs")
print("ping_ms=%s" % (("%.0f"%float(ping)) if ping!="?" else "?"))
print("down_mbps=%s" % mbps(g(s,"downlinkThroughputBps")))
print("up_mbps=%s" % mbps(g(s,"uplinkThroughputBps")))
print("sw_version=%s" % g(s,"deviceInfo","softwareVersion"))
al = s.get("alerts") if isinstance(s,dict) else None
active = [k for k,v in al.items() if v] if isinstance(al,dict) else []
print("alerts=%s" % (",".join(active) if active else "none"))
'
}
dish_age_s() {  # seconds since the cache was last refreshed (empty if no cache) — for the cache-only hot path
  [ -s "$DISHCACHE" ] || return 1
  local m; m=$(stat -f %m "$DISHCACHE" 2>/dev/null) || return 1
  echo $(( $(date +%s) - m ))
}
dish() {  # CLI: bare=live summary (+refresh cache) | --raw=raw grpcurl json | --json=flat parsed fields
  case "${1:-}" in
    --raw)  dish_fetch; return $? ;;
    --json) local r rc; r=$(dish_fetch); rc=$?; [ "$rc" -ne 0 ] && { echo "$r"; return "$rc"; }; printf '%s\n' "$r" | dish_parse; return 0 ;;
  esac
  local raw rc; raw=$(dish_fetch); rc=$?
  [ "$rc" -ne 0 ] && { echo "🛰  $raw"; return "$rc"; }
  local state="?" uptime_s="?" obstruction_pct="?" ping_ms="?" down_mbps="?" up_mbps="?" sw_version="?" alerts="?" k v
  while IFS='=' read -r k v; do case "$k" in
      state) state=$v;; uptime_s) uptime_s=$v;; obstruction_pct) obstruction_pct=$v;;
      ping_ms) ping_ms=$v;; down_mbps) down_mbps=$v;; up_mbps) up_mbps=$v;;
      sw_version) sw_version=$v;; alerts) alerts=$v;; esac
  done <<EOF
$(printf '%s\n' "$raw" | dish_parse)
EOF
  local up_h; up_h=$([ "$uptime_s" = "?" ] && echo "?" || echo "$(( uptime_s / 3600 ))h")
  echo "🛰  Starlink dish — ${state}"
  echo "   obstruction ${obstruction_pct}%   ping ${ping_ms}ms   ↓${down_mbps} ↑${up_mbps} Mbps"
  echo "   uptime ${up_h}   sw ${sw_version}   alerts ${alerts}"
}

doctor() {
  echo "🩺 netmode doctor"; echo
  echo "Mode        : $(get_mode)"
  echo "Using now   : $(live_path)  (route via $(route -n get default 2>/dev/null|awk '/interface/{print $2;exit}'))"
  local _gw _ssid; _gw=$(route -n get default 2>/dev/null|awk '/gateway/{print $2;exit}'); _ssid=$(current_ssid 2>/dev/null)
  echo "Network     : class=$(classify_link "$_gw" "$_ssid")  gw=${_gw:-none}  ssid=${_ssid:-none}  $([ "$(classify_link "$_gw" "$_ssid")" = free ] && echo "(uncapped — not billed)")"
  echo "Location    : $(location)$([ -f "$LOC_OVERRIDE" ] && echo " (pinned)")   ·  phone $(phone_present)  ·  Starlink-visible $(ssid_visible "$STARLINK_SSID" && echo yes || echo no)  ·  home-SSIDs learned $([ -s "$HOME_FP" ] && grep -c . "$HOME_FP" || echo 0)"
  local _scn; _scn=$(scan_ssids | grep -c .)
  echo "Sensing     : Wi-Fi scan sees ${_scn} SSIDs$([ "${_scn:-0}" -lt 2 ] && echo "  ⚠ very few — SSID/location sensing degrades if macOS Location Services is OFF for the scanner; until restored, location holds last/UNKNOWN (won't wrongly grab Starlink)")"
  echo "Net trigger : $(launchctl list 2>/dev/null | grep -q netmode.netwatch && echo "armed (reacts to network changes)" || echo "not installed — \`netmode trigger install\`")"
  echo "Keep-alive  : $(launchctl list 2>/dev/null | grep -q netmode.keepalive && echo "on (stops iPhone hotspot idle-drops while you're working)" || echo "off — \`netmode keepalive on\`")"
  echo "iPhone USB  : $(usb_up && echo "up $(ipconfig getifaddr "$USBIF")" || echo down)"
  echo "Wi-Fi       : $(wifi_state_str)  ip=$(wifi_ip||echo none)"
  local pl ploss sl sloss; health_record; read -r pl ploss sl sloss < "$HEALTH"
  local pld sld; pld=$([ "${pl:-down}" = down ] && echo "no internet" || echo "lat=${pl}ms loss=${ploss}%")
  sld=$([ "${sl:-down}" = down ] && echo "not on Starlink" || echo "lat=${sl}ms loss=${sloss}%")
  echo "Phone link  : ${pld}  score=$(link_score "$pl" "$ploss")/100"
  echo "Starlnk link: ${sld}  score=$(link_score "$sl" "$sloss")/100"
  local sm; sm=$(schedule_match "$(date +%H%M)")
  echo "Schedule    : $([ -n "$sm" ] && echo "active window → $sm" || echo "no active window")"
  if [ -s "$ANCHORWIN" ]; then local _as _ae; read -r _as _ae < "$ANCHORWIN"
    echo "Overnight   : Starlink ${_as}–${_ae} (home only)$(in_anchor_window "$(date +%H%M)" && echo "  ← ACTIVE now: backups ride Starlink, sparing the phone cap")"
  else echo "Overnight   : off  (home is iPhone-only around the clock · \`netmode overnight 0100 0700\` to let backups ride Starlink)"; fi
  local _dage; _dage=$(dish_age_s 2>/dev/null)   # cache-only — doctor never blocks on a live dish poll
  if [ -n "$_dage" ]; then local _ds="?" _do="?" _dp="?" _k _v
    while IFS='=' read -r _k _v; do case "$_k" in state) _ds=$_v;; obstruction_pct) _do=$_v;; ping_ms) _dp=$_v;; esac; done <<EOF
$(dish_parse < "$DISHCACHE")
EOF
    echo "Dish        : ${_ds}  obstruction ${_do}%  ping ${_dp}ms  (cached ${_dage}s ago · \`netmode dish\` to refresh)"
  else echo "Dish        : $(command -v grpcurl >/dev/null 2>&1 && echo "n/a — run \`netmode dish\` on the Starlink LAN" || echo "grpcurl not installed (\`brew install grpcurl\`) — dish stats optional, read-only")"; fi
  echo "Service ord : $(networksetup -listnetworkserviceorder 2>/dev/null | awk '/\([0-9]\)/{printf "%s ",$0}' | sed 's/([0-9]) //g')"
  echo "Wi-Fi pref  : $(networksetup -listpreferredwirelessnetworks "$WIFI" 2>/dev/null | sed 's/^[[:space:]]*//' | tr '\n' ',' | sed 's/,$//')"
  echo "DNS (wifi)  : $(networksetup -getdnsservers Wi-Fi 2>/dev/null | tr '\n' ' ')"
  echo "launchd     : $(launchctl list 2>/dev/null | grep -q netmeter && echo loaded || echo NOT loaded)"
  echo "Dashboard   : $(curl -s -m1 http://127.0.0.1:$DASH_PORT/status.json >/dev/null 2>&1 && echo "up :$DASH_PORT" || echo down)"
  echo "Next move   : $(plan_line)"
  echo; report
}

jstr() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
json() {
  local pb sb fb pg sg fg ppct spct pl ploss sl sloss pscore sscore wstate sched
  pb=$(usage_get phone); sb=$(usage_get starlink); fb=$(usage_get free)
  pg=$(gbf "$pb"); sg=$(gbf "$sb"); fg=$(gbf "$fb")
  ppct=$(awk -v g="$pg" -v c="$PHONE_CAP_GB" 'BEGIN{if(c<=0){print 0}else{x=(g/c)*100; if(x>100)x=100; printf "%.0f",x}}')
  spct=$(awk -v g="$sg" -v c="$STARLINK_CAP_GB" 'BEGIN{if(c<=0){print 0}else{x=(g/c)*100; if(x>100)x=100; printf "%.0f",x}}')
  local p_next p_left p_proj p_tocap p_doy p_dic s_next s_left s_proj s_tocap
  project phone;    p_next=$CNEXT; p_left=$DLEFT; p_proj=$PROJ; p_tocap=$DTOCAP; p_doy=$DOY; p_dic=$DIC
  project starlink; s_next=$CNEXT; s_left=$DLEFT; s_proj=$PROJ; s_tocap=$DTOCAP
  if [ -f "$HEALTH" ]; then read -r pl ploss sl sloss < "$HEALTH"; else pl="?"; ploss="?"; sl="?"; sloss="?"; fi
  pscore=$(link_score "${pl:-down}" "${ploss:-100}"); sscore=$(link_score "${sl:-down}" "${sloss:-100}")
  sched=$(schedule_match "$(date +%H%M)")
  wstate=$(wifi_state_str)
  local m using eff uclass
  m=$(get_mode); using=$(live_path); eff="phone"; [ -f "$AUTOSTATE" ] && eff=$(cat "$AUTOSTATE")
  uclass=$(classify_link "$(route -n get default 2>/dev/null | awk '/gateway/{print $2;exit}')" "$(current_ssid 2>/dev/null)")
  printf '{'
  printf '"mode":"%s",' "$m"
  printf '"auto_state":"%s",' "$eff"
  printf '"using":"%s",' "$using"
  printf '"using_class":"%s",' "$uclass"
  printf '"location":"%s",' "$(location_cached)"
  printf '"location_pinned":%s,' "$( [ -f "$LOC_OVERRIDE" ] && echo true || echo false )"
  printf '"phone_presence":"%s",' "$(presence_cached)"
  printf '"starlink_visible":%s,' "$( [ "$(sense_field star)" = true ] && echo true || echo false )"
  printf '"anchor_window":"%s",' "$( [ -s "$ANCHORWIN" ] && tr -d '\n' < "$ANCHORWIN" )"
  printf '"anchor_active":%s,' "$( in_anchor_window "$(date +%H%M)" && echo true || echo false )"
  # dish: cache-only here (never invokes grpcurl on the hot path). reachable = cheap proxy (we're on the Starlink LAN).
  printf '"dish_available":%s,' "$( command -v grpcurl >/dev/null 2>&1 && echo true || echo false )"
  printf '"dish_reachable":%s,' "$( [ "$uclass" = starlink ] && echo true || echo false )"
  if [ -s "$DISHCACHE" ]; then
    local _dstate="?" _dobs="?" _dping="?" _dage _k _v; _dage=$(dish_age_s)
    while IFS='=' read -r _k _v; do case "$_k" in state) _dstate=$_v;; obstruction_pct) _dobs=$_v;; ping_ms) _dping=$_v;; esac; done <<EOF
$(dish_parse < "$DISHCACHE")
EOF
    printf '"dish_state":"%s",'      "$_dstate"
    printf '"dish_obstruction":"%s",' "$_dobs"
    printf '"dish_ping_ms":"%s",'    "$_dping"
    printf '"dish_age_s":%s,'        "${_dage:-null}"
  else
    printf '"dish_state":null,"dish_obstruction":null,"dish_ping_ms":null,"dish_age_s":null,'
  fi
  printf '"net_trigger":%s,' "$( launchctl list 2>/dev/null | grep -q netmode.netwatch && echo true || echo false )"
  printf '"keepalive":%s,' "$( launchctl list 2>/dev/null | grep -q netmode.keepalive && echo true || echo false )"
  printf '"switching":%s,' "$( [ -f "$LOCK" ] && echo true || echo false )"
  printf '"phone_up":%s,' "$( usb_up && echo true || echo false )"
  printf '"phone_ip":"%s",' "$(ipconfig getifaddr "$USBIF" 2>/dev/null||echo down)"
  printf '"phone_lat":"%s",' "$pl"
  printf '"phone_loss":"%s",' "$ploss"
  printf '"phone_score":%s,' "${pscore:-0}"
  printf '"wifi_ip":"%s",' "$(wifi_ip||echo none)"
  printf '"wifi_lat":"%s",' "$sl"
  printf '"wifi_loss":"%s",' "$sloss"
  printf '"wifi_score":%s,' "${sscore:-0}"
  printf '"wifi_state":"%s",' "$(jstr "$wstate")"
  printf '"phone_gb":%s,' "$(printf '%.1f' "$pg")"
  printf '"starlink_gb":%s,' "$(printf '%.1f' "$sg")"
  printf '"free_gb":%s,' "$(printf '%.1f' "$fg")"
  printf '"phone_cap":%s,' "$PHONE_CAP_GB"
  printf '"starlink_cap":%s,' "$STARLINK_CAP_GB"
  printf '"phone_pct":%s,' "$ppct"
  printf '"starlink_pct":%s,' "$spct"
  printf '"phone_reset_day":%s,' "$PHONE_RESET_DAY"
  printf '"starlink_reset_day":%s,' "$STARLINK_RESET_DAY"
  printf '"phone_next":"%s",' "$p_next"
  printf '"starlink_next":"%s",' "$s_next"
  printf '"phone_days_left":%s,' "$p_left"
  printf '"starlink_days_left":%s,' "$s_left"
  printf '"proj_phone_gb":%s,' "${p_proj:-0}"
  printf '"proj_starlink_gb":%s,' "${s_proj:-0}"
  printf '"phone_days_to_cap":"%s",' "$p_tocap"
  printf '"starlink_days_to_cap":"%s",' "$s_tocap"
  printf '"day_of_cycle":%s,' "$p_doy"
  printf '"days_in_cycle":%s,' "$p_dic"
  printf '"days_left":%s,' "$p_left"
  printf '"days_to_cap":"%s",' "$p_tocap"
  printf '"reset_day":%s,' "$PHONE_RESET_DAY"
  printf '"auto_switch":%s,' "$AUTO_SWITCH"
  printf '"auto_recover":%s,' "$AUTO_RECOVER"
  printf '"warn_pct":%s,' "$WARN_PCT"
  printf '"crit_pct":%s,' "$CRIT_PCT"
  printf '"sched":"%s",' "$sched"
  printf '"schedule":['
  local first=1 s e md
  if [ -f "$SCHEDULE" ]; then while read -r s e md; do
    case "$md" in auto|failover|anchor|solo|ladder) ;; *) continue;; esac
    [ "$first" = 1 ] || printf ','; first=0
    printf '"%s %s %s"' "$s" "$e" "$md"
  done < "$SCHEDULE"; fi
  printf '],'
  printf '"next":"%s"' "$(jstr "$(plan_line)")"
  printf '}\n'
}

set_config() {  # set_config KEY VALUE  (only known keys)
  local k="$1" v="$2"
  case "$k" in PHONE_CAP_GB|STARLINK_CAP_GB|PHONE_RESET_DAY|STARLINK_RESET_DAY|RESET_DAY|AUTO_SWITCH|WARN_PCT|CRIT_PCT|AUTO_RECOVER) ;; *) return 1;; esac
  case "$v" in ''|*[!0-9]*) return 1;; esac
  local tmp="$CONFIG.tmp"; grep -v "^$k=" "$CONFIG" > "$tmp" 2>/dev/null; printf '%s=%s\n' "$k" "$v" >> "$tmp"; mv "$tmp" "$CONFIG"
  log_event "config: $k=$v"
}

# anchor a link's CURRENT-cycle usage to a provider-reported number (carrier/Starlink email or app).
# The caps are SHARED across devices (the TV is the big Starlink user), so the provider total is ground
# truth; the live meter then increments on top of it. Usage: netmode setusage starlink 800
setusage() {
  local link="$1" gb="$2"
  case "$link" in phone|starlink|free) ;; *) echo "usage: netmode setusage <phone|starlink|free> <GB>"; return 1;; esac
  case "$gb" in ''|*[!0-9.]*) echo "GB must be a number"; return 1;; esac
  local bytes; bytes=$(awk -v g="$gb" 'BEGIN{printf "%.0f", g*1073741824}')
  usage_set "$link" "$bytes"
  log_event "anchor: $link = ${gb} GB (provider truth)"
  echo "✅ anchored $(link_label "$link") to ${gb} GB for the cycle starting $(link_cyclekey "$link")"
}

# ---- glanceability & CLI suite ---------------------------------------------
watch_loop() {  # dependency-free live view
  local n="${1:-5}"; case "$n" in ''|*[!0-9]*) n=5;; esac
  trap 'printf "\n"; exit 0' INT TERM
  while :; do clear; status; printf '\n  (live — refresh %ss · Ctrl-C to exit)\n' "$n"; sleep "$n"; done
}

why() {  # explain the current decision and the inputs behind it
  local pb sb pl ploss sl sloss m using sched uclass
  pb=$(usage_get phone); sb=$(usage_get starlink)
  [ -f "$HEALTH" ] && read -r pl ploss sl sloss < "$HEALTH"
  m=$(get_mode); using=$(live_path); sched=$(schedule_match "$(date +%H%M)")
  uclass=$(classify_link "$(route -n get default 2>/dev/null|awk '/gateway/{print $2;exit}')" "$(current_ssid 2>/dev/null)")
  echo "🤔 netmode — why"
  echo "  decision : $(plan_line)"
  echo "  mode     : $m$([ -n "$sched" ] && echo "   (schedule window active → $sched)")"
  echo "  using    : $using  (network class: $uclass$([ "$uclass" = free ] && echo " — uncapped"))"
  local plf slf; plf=$([ "${pl:-down}" = down ] && echo "no internet" || echo "${pl}ms loss ${ploss}%")
  slf=$([ "${sl:-down}" = down ] && echo "not on Starlink" || echo "${sl}ms loss ${sloss}%")
  echo "  📱 phone : $(gb "$pb")/${PHONE_CAP_GB} GB (resets $(cycle_next "$PHONE_RESET_DAY")) · score $(link_score "${pl:-down}" "${ploss:-100}")/100 ($plf)"
  echo "  🛰 star  : $(gb "$sb")/${STARLINK_CAP_GB} GB (resets $(cycle_next "$STARLINK_RESET_DAY")) · score $(link_score "${sl:-down}" "${sloss:-100}")/100 ($slf)"
  local loc; loc=$(location)
  echo "  location : $loc$([ -f "$LOC_OVERRIDE" ] && echo " (manually pinned)")  ·  phone $(phone_present)"
  echo "  presence : USB $(usb_up && echo up || echo down) · phone-Wi-Fi $(on_phone_wifi && echo yes || echo no) · phone-SSID-seen $(ssid_visible "$PHONE_SSID" && echo yes || echo no) · Starlink-seen $(ssid_visible "$STARLINK_SSID" && echo yes || echo no)"
  [ "$m" = auto ] && echo "  policy   : auto wants '$(auto_want)'  (phone cap ${PHONE_CAP_GB} GB · auto_switch=$AUTO_SWITCH)"
  [ "$m" = seamless ] && echo "  policy   : seamless → $([ "$loc" = home ] && { in_anchor_window "$(date +%H%M)" && echo "HOME (overnight anchor): Starlink for backups" || echo "HOME: iPhone only, never Starlink"; } || echo "${loc^^}: burn iPhone first, Starlink backup")"
}

export_csv() {  # history.tsv -> CSV on stdout
  echo "date,phone_gb,starlink_gb"
  [ -f "$HISTORY" ] && while IFS=$'\t' read -r d p o; do printf '%s,%s,%s\n' "$d" "$p" "$o"; done < "$HISTORY"
}

menubar_render() {  # emit a SwiftBar/xbar menu from the engine's json (called by the plugin)
  python3 - "$DIR" <<'PY'
import json,sys,subprocess,os
d=sys.argv[1]; nm=os.path.join(d,"netmode.sh")
try: s=json.loads(subprocess.run(["/bin/bash",nm,"json"],capture_output=True,text=True,timeout=15).stdout or "{}")
except Exception: s={}
using=s.get("using","?"); icon={"phone":"📱","starlink":"🛰","offline":"⚠"}.get(using,"🌐")
pct=s.get("phone_pct","?")
loc=s.get("location",""); locicon={"home":" 🏠","away":" 🚶"}.get(loc,"")
print(f"{icon} {pct}%{locicon} | font=Menlo")
print("---")
print((s.get("next","") or "netmode").replace("|","¦"))
if loc: print(f"location: {loc}{' (pinned)' if s.get('location_pinned') else ''} · phone {s.get('phone_presence','?')}")
print(f"📱 iPhone {s.get('phone_gb','?')}/{s.get('phone_cap','?')}GB ({pct}%) · score {s.get('phone_score','?')}")
print(f"🛰 Starlink {s.get('starlink_gb','?')}/{s.get('starlink_cap','?')}GB · score {s.get('wifi_score','?')}")
print("---")
for label,mode in [("Observe only","observe"),("✨ Seamless","seamless"),("⚡ Auto","auto"),("Failover","failover"),("Anchor","anchor"),("Solo","solo"),("Ladder","ladder"),("📱 Grab iPhone now","phone")]:
    mark="✓ " if s.get("mode")==mode else "  "
    print(f"{mark}{label} | bash=/bin/bash param1={nm} param2=apply param3={mode} terminal=false refresh=true")
print("---")
print(f"Open dashboard | bash=/bin/bash param1={nm} param2=ui terminal=false")
PY
}

menubar() {  # install (or render) the menu-bar plugin; no daemon of ours
  case "$1" in render) menubar_render; return;; esac
  local d pdir=""
  for d in \
    "$HOME/Library/Application Support/SwiftBar/Plugins" \
    "$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null)" \
    "$HOME/Library/Application Support/xbar/plugins" \
    "$HOME/Documents/xbar/plugins"; do
    [ -n "$d" ] && [ -d "$d" ] && { pdir="$d"; break; }
  done
  if [ -z "$pdir" ]; then
    echo "No SwiftBar/xbar plugin folder found."
    echo "  Install:  brew install --cask swiftbar   (then set its plugin folder once), then:"
    echo "            netmode menubar install"
    echo "  SwiftBar hosts the plugin on its own refresh — netmode adds no background daemon."
    return 1
  fi
  local plug="$pdir/netmode.30s.sh"
  printf '#!/bin/bash\nexec /bin/bash "%s" menubar render\n' "$DIR/netmode.sh" > "$plug"
  chmod +x "$plug"
  echo "✅ Installed menu-bar plugin → $plug"
  echo "   Refreshes every 30s via SwiftBar/xbar. No launchd persistence added."
}

# ---- react ON network change, not on a 5-min timer (no always-on daemon) ----
# A LaunchAgent with WatchPaths fires `netmode tick` the instant macOS rewrites its network
# state (unplug/plug the cable, join/leave Wi-Fi). The process runs once and exits — there is
# deliberately NO KeepAlive key, so this is event-triggered, not a persistent daemon.
TRIGLABEL="com.user.netmode.netwatch"
TRIGPLIST="$HOME/Library/LaunchAgents/$TRIGLABEL.plist"
trigger() {
  case "$1" in
    uninstall)
      launchctl bootout "gui/$(id -u)/$TRIGLABEL" 2>/dev/null || launchctl unload "$TRIGPLIST" 2>/dev/null
      rm -f "$TRIGPLIST"; echo "✅ network-change trigger removed"; return 0 ;;
    install|"") ;;
    *) echo "usage: netmode trigger install|uninstall"; return 1 ;;
  esac
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$TRIGPLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$TRIGLABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$DIR/netmode.sh</string><string>tick</string></array>
  <key>WatchPaths</key>
  <array>
    <string>/etc/resolv.conf</string>
    <string>/Library/Preferences/SystemConfiguration</string>
    <string>/var/run/resolv.conf</string>
  </array>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$DIR/netwatch.log</string>
  <key>StandardErrorPath</key><string>$DIR/netwatch.log</string>
</dict>
</plist>
PLIST
  # no KeepAlive on purpose -> fires once per network change, then exits.
  launchctl bootout "gui/$(id -u)/$TRIGLABEL" 2>/dev/null
  if launchctl bootstrap "gui/$(id -u)" "$TRIGPLIST" 2>/dev/null || launchctl load "$TRIGPLIST" 2>/dev/null; then
    echo "✅ network-change trigger installed → reacts instantly to unplug/join (no daemon)."
    echo "   plist: $TRIGPLIST  (WatchPaths, no KeepAlive)"
  else
    echo "⚠ wrote $TRIGPLIST but launchctl load failed — load it from a Terminal:"
    echo "   launchctl bootstrap gui/$(id -u) \"$TRIGPLIST\""
  fi
}

stop_agents() {
  local uid label plist
  uid=$(id -u)
  for label in com.user.netmeter com.user.netmode.netwatch com.user.netmode.keepalive com.user.netmode.recycle; do
    plist="$HOME/Library/LaunchAgents/$label.plist"
    launchctl bootout "gui/$uid" "$plist" >/dev/null 2>&1 || true
    launchctl bootout "gui/$uid/$label" >/dev/null 2>&1 || true
    launchctl disable "gui/$uid/$label" >/dev/null 2>&1 || true
  done
  pgrep -f "$DIR/netmode.sh" 2>/dev/null | while read -r pid; do
    [ "$pid" = "$$" ] && continue
    kill "$pid" >/dev/null 2>&1 || true
  done
  echo "✅ netmode launch agents stopped/disabled (network state left untouched)"
}

# ---- hotspot keep-alive: stop iOS Personal Hotspot idle-disconnect ----------
# iOS turns the Personal Hotspot off after ~90s of no traffic (drops USB tether AND Wi-Fi hotspot,
# cable plugged in or not). A small periodic heartbeat under that window keeps it alive — but it is
# strictly gated so it costs nothing when you don't need it. Like the net-change trigger this uses a
# LaunchAgent with NO KeepAlive key: StartInterval fires the tick and the process exits each time
# (not a resident daemon). It NEVER changes links / preferred networks — read-only re: routing.
KALABEL="com.user.netmode.keepalive"
KAPLIST="$HOME/Library/LaunchAgents/$KALABEL.plist"
user_idle_s() {  # seconds since the last keyboard/mouse input (0 if unknown)
  local ns; ns=$(ioreg -c IOHID 2>/dev/null | awk '/HIDIdleTime/{n=$NF; gsub(/[^0-9]/,"",n); print n; exit}')
  [ -n "$ns" ] && echo $(( ns / 1000000000 )) || echo 0
}
keepalive_should() {  # PURE: args = <gw> <idle_s>; exit 0 iff we should send a heartbeat
  local gw="$1" idle="${2:-0}"
  [ "$gw" = "$PHONE_GW" ] || return 1                  # only when the iPhone hotspot is the active link
  [ "$idle" -le "$KEEPALIVE_IDLE_MAX" ] 2>/dev/null || return 1  # only while you're actually at the Mac
  return 0
}
keepalive_tick() {  # the heartbeat launchd fires; gated, read-only re: links
  local gw; gw=$(route -n get default 2>/dev/null | awk '/gateway/{print $2;exit}')
  keepalive_should "$gw" "$(user_idle_s)" || return 0
  ping -c1 -t2 "$KEEPALIVE_HOST" >/dev/null 2>&1       # tiny external packet = "client active" to the phone
}
keepalive() {
  case "$1" in
    off|uninstall)
      launchctl bootout "gui/$(id -u)/$KALABEL" 2>/dev/null || launchctl unload "$KAPLIST" 2>/dev/null
      rm -f "$KAPLIST"; echo "✅ hotspot keep-alive removed"; return 0 ;;
    tick) keepalive_tick; return 0 ;;
    status|"")
      if launchctl list 2>/dev/null | grep -q "$KALABEL"; then
        echo "hotspot keep-alive: ON — heartbeat every 45s when on the phone + you're at the Mac (idle>${KEEPALIVE_IDLE_MAX}s = naps)"
      else echo "hotspot keep-alive: off — \`netmode keepalive on\`"; fi
      return 0 ;;
    on|install) ;;
    *) echo "usage: netmode keepalive on|off|status"; return 1 ;;
  esac
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$KAPLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$KALABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$DIR/netmode.sh</string><string>keepalive</string><string>tick</string></array>
  <key>StartInterval</key><integer>45</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/keepalive.log</string>
  <key>StandardErrorPath</key><string>$DIR/keepalive.log</string>
</dict>
</plist>
PLIST
  # no KeepAlive key on purpose -> StartInterval fires the tick every 45s, the process exits each time.
  launchctl bootout "gui/$(id -u)/$KALABEL" 2>/dev/null
  if launchctl bootstrap "gui/$(id -u)" "$KAPLIST" 2>/dev/null || launchctl load "$KAPLIST" 2>/dev/null; then
    echo "✅ hotspot keep-alive installed → no more idle drops while you're working."
    echo "   fires only when the phone is your link AND you're at the Mac; ~160KB/day, nothing when idle/away."
    echo "   plist: $KAPLIST  (StartInterval 45s, no KeepAlive)"
  else
    echo "⚠ wrote $KAPLIST but launchctl load failed — load it from a Terminal:"
    echo "   launchctl bootstrap gui/$(id -u) \"$KAPLIST\""
  fi
}

NETMODE_VERSION_FALLBACK="1.6.0"   # used if the VERSION file is missing (e.g. partial install)
version() {  # print the project version: the VERSION file (trimmed) else the baked-in fallback
  local v
  v=$(tr -d ' \t\r\n' < "$DIR/VERSION" 2>/dev/null)
  [ -n "$v" ] && echo "$v" || echo "$NETMODE_VERSION_FALLBACK"
}

# ---- self-test helpers (isolated; no network changes) ----------------------
_st_version() {  # version() prints a non-empty semver-looking string (VERSION file or fallback)
  local out; out=$(version)
  case "$out" in [0-9]*.[0-9]*.[0-9]*) return 0;; *) return 1;; esac
}
_st_keepalive() {  # keepalive_should fires ONLY when the phone is the active link AND the user is present
  keepalive_should "$PHONE_GW" 0 || return 1                              # on phone, active -> yes
  keepalive_should "$PHONE_GW" "$((KEEPALIVE_IDLE_MAX-1))" || return 1    # just under the idle cap -> yes
  keepalive_should "$PHONE_GW" "$((KEEPALIVE_IDLE_MAX+60))" && return 1   # idle/away from Mac -> no
  keepalive_should "$STARLINK_GW" 0 && return 1                           # on Starlink -> never (don't keep TV's link warm)
  keepalive_should "10.0.0.1" 0 && return 1                               # foreign/free Wi-Fi -> no
  keepalive_should "" 0 && return 1                                       # offline -> no
  return 0
}
_st_sched() {  # schedule_match handles normal + wrap-around windows + gaps
  local f OS="$SCHEDULE"; f=$(mktemp); SCHEDULE="$f"
  printf '2300 0700 anchor\n0900 1700 auto\n' > "$f"
  local r1 r2 r3 r4
  r1=$(schedule_match 0030); r2=$(schedule_match 1200); r3=$(schedule_match 0800); r4=$(schedule_match 2330)
  SCHEDULE="$OS"; rm -f "$f"
  [ "$r1" = anchor ] && [ "$r2" = auto ] && [ -z "$r3" ] && [ "$r4" = anchor ]
}
_st_sched_validate() {  # set_schedule keeps only valid lines, normalizes HHMM-HHMM
  local f OS="$SCHEDULE"; f=$(mktemp); SCHEDULE="$f"
  printf 'garbage line\n0100-0700 anchor\n9999 bad mode\n0800 0900 bogusmode\n' | set_schedule >/dev/null 2>&1
  local n first; n=$(wc -l < "$f" | tr -d ' '); first=$(head -1 "$f")
  SCHEDULE="$OS"; rm -f "$f"
  [ "$n" = 1 ] && [ "$first" = "0100 0700 anchor" ]
}
_st_usage() {  # usage_set/get/add round-trip on an isolated per-(link,cycle) store
  local OU="$USAGE" f; f=$(mktemp); USAGE="$f"
  usage_set phone 1000; local a; a=$(usage_get phone)
  usage_add phone 500;  local b; b=$(usage_get phone)
  usage_set starlink 9; local c; c=$(usage_get starlink)   # different link, untouched by phone writes
  local d; d=$(usage_get phone)
  USAGE="$OU"; rm -f "$f" "$f.tmp"
  [ "$a" = 1000 ] && [ "$b" = 1500 ] && [ "$c" = 9 ] && [ "$d" = 1500 ]
}
_st_fp() {  # fp_overlap counts learned home SSIDs present in a scan
  local OF="$HOME_FP" f; f=$(mktemp); HOME_FP="$f"
  printf 'FiOS-OPV9G-5G\nSpectrumSetup-58\nFios-vxTS7\n' > "$f"
  local n; n=$(printf 'FiOS-OPV9G-5G\nSpectrumSetup-58\nSomeCafe\n' | fp_overlap)
  HOME_FP="$OF"; rm -f "$f"
  [ "$n" = 2 ]
}
_st_loc() {  # asymmetric debounce: leaving home needs LEAVE_HOME_SAMPLES(3), returning needs 2
  local OL="$LOCSTATE" f; f=$(mktemp); LOCSTATE="$f"; printf 'home  0\n' > "$f"
  local a b c d e
  a=$(location_commit away)   # 1 away -> still home (leaving home is sticky)
  b=$(location_commit away)   # 2 away -> still home (not enough yet)
  c=$(location_commit away)   # 3 away -> flips to away
  d=$(location_commit home)   # 1 home -> still away (returning needs 2)
  e=$(location_commit home)   # 2 home -> flips back to home
  LOCSTATE="$OL"; rm -f "$f"
  [ "$a" = home ] && [ "$b" = home ] && [ "$c" = away ] && [ "$d" = away ] && [ "$e" = home ]
}
_st_loc_fastaway() {  # strong-away: need=1 leaves home in ONE sample; need-override never strands, default still 3
  local OL="$LOCSTATE" f g; f=$(mktemp); LOCSTATE="$f"; printf 'home  0\n' > "$f"
  local one; one=$(location_commit away 1)            # explicit need=1 -> flips immediately
  g=$(mktemp); LOCSTATE="$g"; printf 'home  0\n' > "$g"
  local s1 s2; s1=$(location_commit away); s2=$(location_commit away)  # default path: still 3-sample sticky
  LOCSTATE="$OL"; rm -f "$f" "$g"
  [ "$one" = away ] && [ "$s1" = home ] && [ "$s2" = home ]
}
_st_loc_strong_guard() {  # location(): strong-away flips in 1; but Starlink-visible -> home (never fast-leave while truly home)
  local OL="$LOCSTATE" f away_committed home_committed; f=$(mktemp)
  away_committed=$(   # healthy foreign scan, no Starlink, 0 overlap -> away in ONE call
    LOCSTATE=$(mktemp); printf 'home  0\n' > "$LOCSTATE"
    ssid_visible(){ return 1; }                 # Starlink not visible
    scan_ssids(){ seq 1 20 | sed 's/^/Net/'; }  # 20 foreign SSIDs
    fp_overlap(){ cat >/dev/null; echo 0; }; fp_learn(){ cat >/dev/null; }
    HOME_FP=$(mktemp); echo HomeNet > "$HOME_FP"
    location; rm -f "$LOCSTATE" "$HOME_FP" )
  home_committed=$(  # SAME scan but Starlink IS visible -> decider says home, fast-leave must NOT fire
    LOCSTATE=$(mktemp); printf 'home  0\n' > "$LOCSTATE"
    ssid_visible(){ return 0; }                 # Starlink visible = at the apartment
    scan_ssids(){ seq 1 20 | sed 's/^/Net/'; }
    fp_overlap(){ cat >/dev/null; echo 0; }; fp_learn(){ cat >/dev/null; }
    HOME_FP=$(mktemp); echo HomeNet > "$HOME_FP"
    location; rm -f "$LOCSTATE" "$HOME_FP" )
  LOCSTATE="$OL"
  [ "$away_committed" = away ] && [ "$home_committed" = home ]
}
_st_fp_deny() {  # fp_learn must drop ubiquitous public SSIDs and keep distinctive ones
  local OF="$HOME_FP" f; f=$(mktemp); HOME_FP="$f"; : > "$f"
  printf 'FiOS-OPV9G-5G\nxfinitywifi\nattwifi\neduroam\nThe Promised LAN\n' | fp_learn
  local kept; kept=$(cat "$f"); HOME_FP="$OF"; rm -f "$f"
  printf '%s\n' "$kept" | grep -qx 'FiOS-OPV9G-5G' \
    && printf '%s\n' "$kept" | grep -qx 'The Promised LAN' \
    && ! printf '%s\n' "$kept" | grep -qiE 'xfinitywifi|attwifi|eduroam'
}
_st_anchorwin() {  # in_anchor_window: inside/outside, wrap-around, empty=off
  local OA="$ANCHORWIN" f ok=1; f=$(mktemp); ANCHORWIN="$f"
  printf '0100 0700\n' > "$f"
  in_anchor_window 0300 || ok=0      # inside
  in_anchor_window 0800 && ok=0      # outside
  printf '2300 0200\n' > "$f"
  in_anchor_window 0000 || ok=0      # wrap-around: inside
  in_anchor_window 0500 && ok=0      # wrap-around: outside
  : > "$f"
  in_anchor_window 0300 && ok=0      # empty file = off
  ANCHORWIN="$OA"; rm -f "$f"
  [ "$ok" = 1 ]
}
_st_anchor_seam() {  # cfg_seamless: HOME in-window -> Starlink path; AWAY in-window -> cascade (never strands)
  local OA="$ANCHORWIN" f; f=$(mktemp); ANCHORWIN="$f"; printf '0000 2400\n' > "$f"  # window = always active
  local home_path away_path
  home_path=$(   # subshell: function overrides stay local
    location_cached(){ echo home; }; on_starlink(){ return 1; }
    cfg_anchor(){ echo STARLINK; }; auto_apply(){ echo CASCADE; }
    order_phone_first(){ :;}; enable_links(){ :;}; wifi_on(){ :;}; pref_remove(){ :;}
    on_phone_wifi(){ return 1;}; usb_up(){ return 1;}; join(){ return 1;}; phone_present(){ echo gone;}
    _anchor_announce_once(){ :;}; log_event(){ :;}; wifi_off(){ :;}; _seamless_hold_notify(){ :;}
    cfg_seamless )
  away_path=$(
    location_cached(){ echo away; }
    cfg_anchor(){ echo STARLINK; }; auto_apply(){ echo CASCADE; }; log_event(){ :;}
    cfg_seamless )
  ANCHORWIN="$OA"; rm -f "$f"
  [ "$home_path" = STARLINK ] && [ "$away_path" = CASCADE ]
}
_st_anchor_backoff() {  # in-window + Starlink unreachable: cfg_anchor runs ONCE, then backs off (no per-tick Wi-Fi storm); cleared outside window
  local OA="$ANCHORWIN" OF="$_ANCHORFAIL" win cnt
  win=$(mktemp); ANCHORWIN="$win"; printf '0000 2400\n' > "$win"   # window = always active
  cnt=$(mktemp); _ANCHORFAIL=$(mktemp); rm -f "$_ANCHORFAIL"       # fail-flag starts unset; cnt tallies cfg_anchor calls
  local stub="
    location_cached(){ echo home; }; on_starlink(){ return 1; };
    cfg_anchor(){ printf x >>'$cnt'; return 1; };
    order_phone_first(){ :;}; enable_links(){ :;}; wifi_on(){ :;}; pref_remove(){ :;};
    on_phone_wifi(){ return 0;}; usb_up(){ return 1;}; join(){ return 1;};
    phone_present(){ echo near;}; _seamless_hold_notify(){ :;}; _anchor_announce_once(){ :;};
    notify(){ :;}; log_event(){ :;}; wifi_off(){ :;};"
  ( eval "$stub"; cfg_seamless )   # tick 1: attempt cfg_anchor -> fail -> set flag, fall to phone
  ( eval "$stub"; cfg_seamless )   # tick 2: flag set -> must NOT power-cycle (cfg_anchor not called again)
  local n; n=$(wc -c < "$cnt" | tr -d ' ')
  local flagset=0 cleared=0
  [ -f "$_ANCHORFAIL" ] && flagset=1
  ( eval "$stub"; in_anchor_window(){ return 1; }; cfg_seamless )   # outside window -> arms a fresh attempt
  [ ! -f "$_ANCHORFAIL" ] && cleared=1
  ANCHORWIN="$OA"; _ANCHORFAIL="$OF"; rm -f "$win" "$cnt"
  [ "$n" = 1 ] && [ "$flagset" = 1 ] && [ "$cleared" = 1 ]
}
_st_seam_home() {  # cfg_seamless HOME, window OFF: phone-present -> phone+pref_remove; phone GONE -> HOLD. NEVER Starlink (cfg_anchor).
  local normal gone
  normal=$(   # home, out of window, phone reachable on its Wi-Fi -> normal phone path, Starlink removed from preferred
    location_cached(){ echo home; }; in_anchor_window(){ return 1; }
    cfg_anchor(){ echo ANCHOR; }   # marker: must NOT appear out of window
    order_phone_first(){ :;}; enable_links(){ :;}; wifi_on(){ :;}
    pref_remove(){ echo "PREFRM:$1"; }; on_phone_wifi(){ return 0; }
    cfg_seamless )
  gone=$(   # home, out of window, phone GONE (every reach fails) -> hold/notify, never Starlink
    location_cached(){ echo home; }; in_anchor_window(){ return 1; }
    cfg_anchor(){ echo ANCHOR; }   # marker: must NOT appear
    order_phone_first(){ :;}; enable_links(){ :;}; wifi_on(){ :;}; pref_remove(){ :;}
    on_phone_wifi(){ return 1;}; usb_up(){ return 1;}; join(){ return 1;}
    on_starlink(){ return 1;}; wifi_off(){ :;}; phone_present(){ echo gone;}
    _seamless_hold_notify(){ echo HOLD; }; log_event(){ :;}
    cfg_seamless )
  echo "$normal" | grep -q "PREFRM:$STARLINK" && ! echo "$normal" | grep -q ANCHOR \
    && echo "$gone" | grep -q HOLD && ! echo "$gone" | grep -q ANCHOR
}
_st_dish_parse() {  # dish_parse: extracts fields from a real-shape fixture; missing keys -> ?
  local out; out=$(printf '%s' '{"dishGetStatus":{"deviceState":{"uptimeS":"360000"},"obstructionStats":{"fractionObstructed":0.0123},"popPingLatencyMs":34.7,"downlinkThroughputBps":94000000,"uplinkThroughputBps":12500000,"deviceInfo":{"softwareVersion":"v.test"},"alerts":{"motorsStuck":true,"thermalThrottle":false}}}' | dish_parse)
  echo "$out" | grep -qx 'state=online'        || return 1
  echo "$out" | grep -qx 'obstruction_pct=1.23' || return 1
  echo "$out" | grep -qx 'ping_ms=35'          || return 1
  echo "$out" | grep -qx 'down_mbps=752.0'      || return 1
  echo "$out" | grep -qx 'alerts=motorsStuck'   || return 1   # only the TRUE alert, thermalThrottle dropped
  local sp; sp=$(printf '%s' '{"dishGetStatus":{}}' | dish_parse)
  echo "$sp" | grep -qx 'ping_ms=?'            || return 1
  echo "$sp" | grep -qx 'obstruction_pct=?'    || return 1
  printf '%s' 'not json' | dish_parse | grep -qx 'error=unparseable'   # garbage -> graceful, no crash
}
_st_dish_guard() {  # dish_fetch: degrades on no-grpcurl (rc2) / unreachable (rc3); writes NO cache; touches NO link
  local OC="$DISHCACHE" tc out rc; tc=$(mktemp); rm -f "$tc"; DISHCACHE="$tc"
  out=$(PATH=/nonexistent dish_fetch 2>&1); rc=$?       # grpcurl absent
  { [ "$rc" -eq 2 ] && echo "$out" | grep -qi grpcurl && [ ! -e "$tc" ]; } || { DISHCACHE="$OC"; return 1; }
  local bd mk; bd=$(mktemp -d); printf '#!/bin/sh\nexit 0\n' > "$bd/grpcurl"; chmod +x "$bd/grpcurl"; mk=$(mktemp); rm -f "$mk"
  out=$(                                                 # grpcurl present but dish unreachable
    PATH="$bd:$PATH"; dish_reachable(){ return 1; }
    enable_links(){ echo x>>"$mk";}; cfg_anchor(){ echo x>>"$mk";}; order_phone_first(){ echo x>>"$mk";}
    pref_remove(){ echo x>>"$mk";}; join(){ echo x>>"$mk";}; wifi_off(){ echo x>>"$mk";}
    dish_fetch 2>&1 ); rc=$?
  local ok=1
  { [ "$rc" -eq 3 ] && echo "$out" | grep -qi unreachable && [ ! -e "$tc" ] && [ ! -s "$mk" ]; } || ok=0
  ( PATH=/nonexistent; dish --json >/dev/null 2>&1 ); [ $? -ne 0 ] || ok=0   # CLI must propagate failure rc (not mask as 0)
  ( PATH=/nonexistent; dish --raw  >/dev/null 2>&1 ); [ $? -ne 0 ] || ok=0
  DISHCACHE="$OC"; rm -rf "$bd"; rm -f "$mk" "$tc"
  [ "$ok" -eq 1 ]
}
_st_dish_json() {  # json: dish fields are cache-ONLY — null when no cache, populated from cache, always valid JSON
  local OC="$DISHCACHE" tc; tc=$(mktemp); rm -f "$tc"; DISHCACHE="$tc"
  json | python3 -c 'import sys,json;d=json.load(sys.stdin);assert d["dish_state"] is None and "dish_available" in d and "dish_reachable" in d' \
    || { DISHCACHE="$OC"; rm -f "$tc"; return 1; }
  printf '%s' '{"dishGetStatus":{"deviceState":{"uptimeS":"7200"},"obstructionStats":{"fractionObstructed":0.05},"popPingLatencyMs":40}}' > "$tc"
  json | python3 -c 'import sys,json;d=json.load(sys.stdin);assert d["dish_state"]=="online" and d["dish_ping_ms"]=="40" and d["dish_age_s"] is not None' \
    || { DISHCACHE="$OC"; rm -f "$tc"; return 1; }
  DISHCACHE="$OC"; rm -f "$tc"
}
_st_converge() {  # converge() drains to the LATEST intent even if it changes mid-apply
  local D R OD="$DESIRED" OF="$APPLYFN"; D=$(mktemp); R=$(mktemp); DESIRED="$D"; echo auto > "$D"
  _st_stub() { printf '%s\n' "$1" >> "$R"; [ "$1" = auto ] && printf 'anchor\n' > "$D"; }
  APPLYFN=_st_stub; converge
  local last; last=$(tail -1 "$R" 2>/dev/null)
  DESIRED="$OD"; APPLYFN="$OF"; rm -f "$D" "$R"
  [ "$last" = anchor ]
}

_st_tick_observe_safe() {  # launchd tick must not switch links unless BACKGROUND_SWITCHING=1
  local mk; mk=$(mktemp); rm -f "$mk"
  (
    BACKGROUND_SWITCHING=0
    recycle_clients(){ :; }; sample(){ :; }; health_record(){ :; }; sense_refresh(){ :; }
    notify_check(){ :; }; history_snapshot(){ :; }; get_mode(){ echo seamless; }
    schedule_tick(){ echo schedule >> "$mk"; }
    cfg_seamless(){ echo seamless >> "$mk"; }
    auto_apply(){ echo auto >> "$mk"; }
    ensure_starlink_standby(){ echo standby >> "$mk"; }
    enforce(){ echo enforce >> "$mk"; }
    wifi_off(){ echo wifi_off >> "$mk"; }
    auto_recover(){ echo recover >> "$mk"; }
    tick
  )
  local ok=1
  [ ! -s "$mk" ] || ok=0
  rm -f "$mk"
  [ "$ok" = 1 ]
}

_st_tick_switch_optin() {  # explicit opt-in preserves old managed behavior
  local mk; mk=$(mktemp); rm -f "$mk"
  (
    BACKGROUND_SWITCHING=1
    recycle_clients(){ :; }; sample(){ :; }; health_record(){ :; }; sense_refresh(){ :; }
    notify_check(){ :; }; history_snapshot(){ :; }; get_mode(){ echo seamless; }
    schedule_tick(){ echo schedule >> "$mk"; }
    cfg_seamless(){ echo seamless >> "$mk"; }
    auto_recover(){ echo recover >> "$mk"; }
    tick
  )
  local out; out=$(cat "$mk" 2>/dev/null); rm -f "$mk"
  echo "$out" | grep -q schedule && echo "$out" | grep -q seamless && echo "$out" | grep -q recover
}

_st_live_path() {  # live_path delegates to classify_link: foreign gw -> free (not bogus 'starlink'); no iface -> offline
  local _LP_IF=en0 _LP_GW _LP_SSID a b c d
  route()        { printf 'gateway: %s\ninterface: %s\n' "$_LP_GW" "$_LP_IF"; }   # stub the only IO live_path does
  current_ssid() { printf '%s\n' "$_LP_SSID"; }
  _LP_GW="$PHONE_GW";    _LP_SSID="";          a=$(live_path)   # iPhone subnet -> phone
  _LP_GW="$STARLINK_GW"; _LP_SSID="";          b=$(live_path)   # TV's Starlink gw -> starlink
  _LP_GW=192.168.200.1;  _LP_SSID="";          c=$(live_path)   # foreign café gw, SSID unreadable -> free (the bug)
  _LP_IF="";             _LP_GW=192.168.200.1; d=$(live_path)   # no default route -> offline
  [ "$a" = phone ] && [ "$b" = starlink ] && [ "$c" = free ] && [ "$d" = offline ]
}

# ---- self-test: assert the decision logic & invariants (no network changes) -
selftest() {
  local pass=0 fail=0
  local EVENTS; EVENTS=$(mktemp)   # isolate: helpers that log_event (e.g. set_schedule) must not touch the real events.log
  trap 'rm -f "$EVENTS" "$EVENTS.tmp"' RETURN
  t() { if ( eval "$2" ) >/dev/null 2>&1; then pass=$((pass+1)); printf '  ✅ %s\n' "$1"
        else fail=$((fail+1)); printf '  ❌ %s\n' "$1"; fi; }
  echo "🧪 netmode selftest"
  cycle_dates; project
  t "cycle day within 1..days-in-cycle"        '[ "$DOY" -ge 1 ] && [ "$DOY" -le "$DIC" ]'
  t "days-left is non-negative"                '[ "$DLEFT" -ge 0 ]'
  t "cycle key matches cycle start"            '[ "$CKEY" = "${CSTART%-*}" ]'
  t "gb(1 GiB) == 1.0"                          '[ "$(gb 1073741824)" = "1.0" ]'
  t "gbf(1 GiB) == 1.000"                       '[ "$(gbf 1073741824)" = "1.000" ]'
  t "over_cap true at 600GB (cap 500)"          'PHONE_CAP_GB=500 over_cap_calc 644245094400'
  t "over_cap false at 100GB (cap 500)"         '! PHONE_CAP_GB=500 over_cap_calc 107374182400'
  t "policy: AUTO_SWITCH=0 always wants phone"  '[ "$(AUTO_SWITCH=0 auto_want)" = phone ]'
  t "json is valid JSON"                        'json | python3 -c "import sys,json;json.load(sys.stdin)"'
  t "json carries a non-empty next-move"        'json | python3 -c "import sys,json;assert json.load(sys.stdin)[\"next\"]"'
  t "background switching defaults off"         '! background_switching_enabled'
  t "tick observe-only does not call switch actuators" '_st_tick_observe_safe'
  t "tick switching can be explicitly opted in" '_st_tick_switch_optin'
  t "phone gateway is the iPhone subnet"        'case "$PHONE_GW" in 172.20.10.*) true;; *) false;; esac'
  t "config file present"                       '[ -f "$CONFIG" ]'
  t "plan_line emits a sentence"               '[ -n "$(plan_line)" ]'
  t "link_score 20ms/0% is high"               '[ "$(link_score 20 0)" -ge 90 ]'
  t "link_score 200ms/50% is low"              '[ "$(link_score 200 50)" -le 20 ]'
  t "link_score down == 0"                      '[ "$(link_score down 100)" = 0 ]'
  t "link_score is loss-monotonic"             '[ "$(link_score 20 0)" -gt "$(link_score 20 40)" ]'
  t "classify: phone gateway -> phone"         '[ "$(classify_link "$PHONE_GW" "")" = phone ]'
  t "classify: starlink gateway -> starlink"   '[ "$(classify_link "$STARLINK_GW" "")" = starlink ]'
  t "classify: starlink SSID -> starlink"      '[ "$(classify_link 10.9.9.1 "$STARLINK_SSID")" = starlink ]'
  t "classify: any other network -> free"      '[ "$(classify_link 10.9.9.1 SomeCafe) " = "free " ]'
  t "live_path: foreign gw -> free, not starlink (+phone/starlink/offline)" '_st_live_path'
  t "phone & starlink reset days differ"       '[ "$PHONE_RESET_DAY" != "$STARLINK_RESET_DAY" ]'
  t "cycle_next is after cycle_start"          '[ "$(epoch "$(cycle_next 13)")" -gt "$(epoch "$(cycle_start 13)")" ]'
  t "usage_set/get/add round-trips per link"   '_st_usage'
  t "over_cap uses passed cap (1000)"          'over_cap_calc 1181116006400 1000 && ! over_cap_calc 1181116006400 2000'
  t "schedule_match wrap+windows+gaps"         '_st_sched'
  t "set_schedule rejects junk lines"          '_st_sched_validate'
  t "apply converges to the latest intent"     '_st_converge'
  t "json carries phone_score"                 'json | python3 -c "import sys,json;assert \"phone_score\" in json.load(sys.stdin)"'
  t "json carries a schedule array"            'json | python3 -c "import sys,json;assert isinstance(json.load(sys.stdin)[\"schedule\"],list)"'
  t "json carries per-link reset days"         'json | python3 -c "import sys,json;d=json.load(sys.stdin);assert d[\"phone_reset_day\"] and d[\"starlink_reset_day\"]"'
  t "json carries free_gb + using_class"       'json | python3 -c "import sys,json;d=json.load(sys.stdin);assert \"free_gb\" in d and \"using_class\" in d"'
  # --- seamless / location / presence ---
  t "phone_decide: USB up -> tethered"          '[ "$(phone_decide 1 0 0 0)" = tethered ]'
  t "phone_decide: on phone-Wi-Fi -> tethered"  '[ "$(phone_decide 0 0 1 0)" = tethered ]'
  t "phone_decide: only SSID seen -> near"       '[ "$(phone_decide 0 1 0 0)" = near ]'
  t "phone_decide: only BT in range -> near"     '[ "$(phone_decide 0 0 0 1)" = near ]'
  t "phone_decide: nothing -> gone"              '[ "$(phone_decide 0 0 0 0)" = gone ]'
  t "location_decide: Starlink seen -> home"     '[ "$(location_decide 1 0 0 5)" = home ]'
  t "location_decide: fingerprint hit -> home"   '[ "$(location_decide 0 2 1 5)" = home ]'
  t "location_decide: no anchors -> away"        '[ "$(location_decide 0 0 1 5)" = away ]'
  t "location_decide: nothing in range -> unknown" '[ "$(location_decide 0 0 0 0)" = unknown ]'
  t "location_decide: degraded scan at home -> unknown" '[ "$(location_decide 0 0 1 1)" = unknown ]'
  t "fp_overlap counts learned SSIDs in scan"    '_st_fp'
  t "fp_learn drops ubiquitous SSIDs"            '_st_fp_deny'
  t "location debounce: leaving home needs 3, returning 2" '_st_loc'
  t "location: strong-away leaves home in 1, default still 3" '_st_loc_fastaway'
  t "location: strong-away fires only when Starlink absent (home stays home)" '_st_loc_strong_guard'
  t "in_anchor_window: in/out + wrap + empty=off" '_st_anchorwin'
  t "seamless: overnight window home->Starlink, away->cascade" '_st_anchor_seam'
  t "seamless: anchor Starlink-unreachable -> tries once, backs off, no Wi-Fi storm" '_st_anchor_backoff'
  t "seamless home off-window: phone present->phone, gone->HOLD, never Starlink" '_st_seam_home'
  t "json carries anchor_window + anchor_active"  'json | python3 -c "import sys,json;d=json.load(sys.stdin);assert \"anchor_window\" in d and \"anchor_active\" in d"'
  t "dish_parse: fields + missing->? + garbage-safe" '_st_dish_parse'
  t "dish_fetch: no-grpcurl/unreachable degrade, no cache, no link touch" '_st_dish_guard'
  t "json: dish cache-only (null w/o cache, valid JSON)" '_st_dish_json'
  t "apply_mode accepts observe"                 'APPLYFN=true; _t=$(mktemp); DESIRED=$_t; printf observe>"$_t"; converge; rm -f "$_t"'
  t "seamless is dispatchable in apply_one"      'type do_seamless >/dev/null 2>&1 && case "seamless" in observe|seamless|auto|failover|anchor|solo|ladder|phone) true;; *) false;; esac'
  t "json carries location + phone_presence"     'json | python3 -c "import sys,json;d=json.load(sys.stdin);assert d[\"location\"] and d[\"phone_presence\"]"'
  t "json carries net_trigger flag"              'json | python3 -c "import sys,json;assert \"net_trigger\" in json.load(sys.stdin)"'
  t "keepalive: heartbeat only on phone + user present" '_st_keepalive'
  t "json carries keepalive flag"                'json | python3 -c "import sys,json;assert \"keepalive\" in json.load(sys.stdin)"'
  t "version prints a semver string"             '_st_version'
  echo "──────────────────────────────────────────────"
  echo "  $pass passed, $fail failed"
  [ "$fail" -eq 0 ]
}

[ "${1:-}" = selftest ] || migrate_default   # migrate old default-like modes to observe once (skips selftest)
case "${1:-status}" in
  observe|pause) do_observe; echo "✅ observe-only"; status ;;
  seamless) do_seamless; echo "✅ seamless"; status ;;
  auto)     do_auto;     echo "✅ auto";     status ;;
  here)     loc_set home ;;
  out)      loc_set away ;;
  unpin)    loc_clear ;;
  trigger)  trigger "$2" ;;
  keepalive) keepalive "$2" ;;            # hotspot heartbeat: on|off|status|tick (stops iOS idle-disconnect)
  stop|panic) stop_agents ;;
  phone)    do_phone;    echo "✅ grabbing iPhone"; status ;;
  failover) do_failover; echo "✅ failover"; status ;;
  anchor)   do_anchor;   echo "✅ anchor";   status ;;
  solo)     do_solo;     echo "✅ solo";     status ;;
  ladder)   do_ladder;   echo "✅ ladder";   status ;;
  apply)    apply_mode "$2" ;;          # serialized, last-writer-wins (used by the dashboard)
  tick)     tick ;;
  recycle)  recycle_clients ;;          # net switched? drop stale client sockets (no policy/mode changes)
  enforce)  enforce ;;
  sample)   sample ;;
  report)   report ;;
  doctor)   doctor ;;
  why)      why ;;
  watch)    watch_loop "$2" ;;
  export)   export_csv ;;
  menubar)  menubar "$2" ;;
  overnight) anchor_window "$2" "$3" ;;  # overnight Starlink window (home only): "HHMM HHMM" | off | show
  dish)     dish "$2" ;;                 # read-only Starlink dish stats (live; needs grpcurl + on Starlink LAN)
  schedule-set) set_schedule ;;         # reads rules on stdin
  setusage) setusage "$2" "$3" ;;       # anchor a link to a provider-reported GB number
  json)     json ;;
  selftest) selftest ;;
  version|--version|-v) version ;;       # print the project version (from the VERSION file)
  config)   set_config "$2" "$3" ;;
  ui)       "$DIR/netui" ;;
  status|"") status ;;
  *) echo "usage: netmode observe|seamless|auto|phone|failover|anchor|solo|ladder | stop | here|out|unpin | overnight HHMM HHMM|off | dish [--raw|--json] | trigger install|uninstall | keepalive on|off|status | watch|why|report|doctor|export|setusage|menubar|selftest|json|ui|version"; status ;;
esac
