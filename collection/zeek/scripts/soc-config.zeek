@load policy/tuning/json-logs.zeek

redef LogAscii::use_json = T;
redef LogAscii::json_timestamps = JSON::TS_ISO8601;

event zeek_init() {
    print "Zeek initialized for SOC platform - outputting JSON logs";
}
