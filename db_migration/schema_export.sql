--
-- PostgreSQL database dump
--

-- Dumped from database version 16.10 (0374078)
-- Dumped by pg_dump version 17.5

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: create_heartbeat_partition(date); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.create_heartbeat_partition(partition_date date) RETURNS void
    LANGUAGE plpgsql
    AS $$
        DECLARE
            partition_name TEXT;
            start_date TIMESTAMP;
            end_date TIMESTAMP;
        BEGIN
            partition_name := 'device_heartbeats_' || to_char(partition_date, 'YYYYMMDD');
            start_date := partition_date;
            end_date := partition_date + INTERVAL '1 day';
            
            -- Check if partition already exists
            IF NOT EXISTS (
                SELECT 1 FROM pg_class WHERE relname = partition_name
            ) THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF device_heartbeats FOR VALUES FROM (%L) TO (%L)',
                    partition_name, start_date, end_date
                );
                
                -- Create indexes
                EXECUTE format(
                    'CREATE INDEX idx_%I_device_ts ON %I (device_id, ts DESC)',
                    partition_name, partition_name
                );
                
                EXECUTE format(
                    'CREATE UNIQUE INDEX idx_%I_dedupe ON %I (device_id, date_trunc(%L, ts), ((EXTRACT(EPOCH FROM ts)::bigint / 10) %% 6))',
                    partition_name, partition_name, 'minute'
                );
                
                RAISE NOTICE 'Created partition %', partition_name;
            END IF;
        END;
        $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: alert_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_states (
    id integer NOT NULL,
    device_id character varying NOT NULL,
    condition character varying NOT NULL,
    state character varying NOT NULL,
    last_raised_at timestamp without time zone,
    last_recovered_at timestamp without time zone,
    cooldown_until timestamp without time zone,
    consecutive_violations integer NOT NULL,
    last_value character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: alert_states_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.alert_states_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: alert_states_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.alert_states_id_seq OWNED BY public.alert_states.id;


--
-- Name: apk_deployment_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.apk_deployment_stats (
    build_id integer NOT NULL,
    total_checks integer NOT NULL,
    total_eligible integer NOT NULL,
    total_downloads integer NOT NULL,
    installs_success integer NOT NULL,
    installs_failed integer NOT NULL,
    verify_failed integer NOT NULL,
    last_updated timestamp without time zone NOT NULL
);


--
-- Name: apk_download_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.apk_download_events (
    event_id bigint NOT NULL,
    build_id integer NOT NULL,
    source character varying NOT NULL,
    token_id character varying,
    admin_user character varying,
    ip character varying,
    ts timestamp without time zone NOT NULL
);


--
-- Name: apk_download_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.apk_download_events_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: apk_download_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.apk_download_events_event_id_seq OWNED BY public.apk_download_events.event_id;


--
-- Name: apk_installations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.apk_installations (
    id integer NOT NULL,
    device_id character varying(100) NOT NULL,
    completed_at timestamp without time zone,
    status character varying(50) NOT NULL,
    error_message text,
    apk_version_id integer NOT NULL,
    initiated_at timestamp without time zone NOT NULL,
    download_progress integer,
    initiated_by character varying,
    download_start_time timestamp without time zone,
    download_end_time timestamp without time zone,
    bytes_downloaded integer,
    avg_speed_kbps integer,
    cache_hit boolean DEFAULT false
);


--
-- Name: apk_installations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.apk_installations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: apk_installations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.apk_installations_id_seq OWNED BY public.apk_installations.id;


--
-- Name: apk_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.apk_versions (
    id integer NOT NULL,
    version_name character varying(50) NOT NULL,
    version_code integer NOT NULL,
    file_path text NOT NULL,
    file_size integer NOT NULL,
    uploaded_at timestamp without time zone NOT NULL,
    uploaded_by character varying(100),
    is_active boolean NOT NULL,
    package_name character varying DEFAULT 'com.example.app'::character varying NOT NULL,
    notes text,
    build_type character varying,
    ci_run_id character varying,
    git_sha character varying,
    signer_fingerprint character varying,
    storage_url text,
    is_current boolean DEFAULT false NOT NULL,
    staged_rollout_percent integer DEFAULT 100 NOT NULL,
    promoted_at timestamp without time zone,
    promoted_by character varying,
    rollback_from_build_id integer,
    wifi_only boolean DEFAULT true NOT NULL,
    must_install boolean DEFAULT false NOT NULL,
    sha256 character varying(64)
);


--
-- Name: apk_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.apk_versions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: apk_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.apk_versions_id_seq OWNED BY public.apk_versions.id;


--
-- Name: auto_relaunch_defaults; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auto_relaunch_defaults (
    id integer NOT NULL,
    enabled boolean NOT NULL,
    package character varying NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: auto_relaunch_defaults_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.auto_relaunch_defaults_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: auto_relaunch_defaults_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.auto_relaunch_defaults_id_seq OWNED BY public.auto_relaunch_defaults.id;


--
-- Name: battery_whitelist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.battery_whitelist (
    id integer NOT NULL,
    package_name character varying(255) NOT NULL,
    added_at timestamp without time zone NOT NULL,
    added_by character varying(100),
    app_name character varying NOT NULL,
    enabled boolean NOT NULL
);


--
-- Name: battery_whitelist_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.battery_whitelist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: battery_whitelist_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.battery_whitelist_id_seq OWNED BY public.battery_whitelist.id;


--
-- Name: bloatware_packages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bloatware_packages (
    id integer NOT NULL,
    package_name character varying NOT NULL,
    enabled boolean NOT NULL,
    description character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: bloatware_packages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bloatware_packages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bloatware_packages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bloatware_packages_id_seq OWNED BY public.bloatware_packages.id;


--
-- Name: bulk_commands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bulk_commands (
    id character varying NOT NULL,
    type character varying NOT NULL,
    payload jsonb NOT NULL,
    targets jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by character varying,
    total_targets integer NOT NULL,
    sent_count integer NOT NULL,
    acked_count integer NOT NULL,
    error_count integer NOT NULL,
    status character varying NOT NULL,
    completed_at timestamp without time zone
);


--
-- Name: command_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.command_results (
    id bigint NOT NULL,
    command_id character varying NOT NULL,
    device_id character varying NOT NULL,
    correlation_id character varying NOT NULL,
    status character varying NOT NULL,
    message text,
    sent_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: command_results_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.command_results_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: command_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.command_results_id_seq OWNED BY public.command_results.id;


--
-- Name: commands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commands (
    id integer NOT NULL,
    request_id character varying(100) NOT NULL,
    device_id character varying(100) NOT NULL,
    command_type character varying(50) NOT NULL,
    parameters text,
    created_at timestamp without time zone NOT NULL,
    completed_at timestamp without time zone,
    status character varying(50) NOT NULL,
    result text,
    error_message text
);


--
-- Name: commands_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.commands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: commands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.commands_id_seq OWNED BY public.commands.id;


--
-- Name: device_commands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_commands (
    id integer NOT NULL,
    device_id character varying NOT NULL,
    type character varying NOT NULL,
    status character varying NOT NULL,
    correlation_id character varying NOT NULL,
    payload jsonb,
    error text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    created_by character varying
);


--
-- Name: device_commands_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.device_commands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: device_commands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.device_commands_id_seq OWNED BY public.device_commands.id;


--
-- Name: device_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_events (
    id integer NOT NULL,
    device_id character varying(100) NOT NULL,
    event_type character varying(50) NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    details text
);


--
-- Name: device_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.device_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: device_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.device_events_id_seq OWNED BY public.device_events.id;


--
-- Name: device_heartbeats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats (
    hb_id bigint NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
)
PARTITION BY RANGE (ts);


--
-- Name: device_heartbeats_hb_id_seq1; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.device_heartbeats_hb_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: device_heartbeats_hb_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.device_heartbeats_hb_id_seq1 OWNED BY public.device_heartbeats.hb_id;


--
-- Name: device_heartbeats_20251022; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251022 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251023; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251023 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251024; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251024 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251025; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251025 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251026; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251026 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251027; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251027 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251028; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251028 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251029; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251029 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251030; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251030 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251031; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251031 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251101; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251101 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251102; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251102 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251103; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251103 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251104; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251104 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251105; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251105 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251106; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251106 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251107; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251107 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251108; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251108 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251109; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251109 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251110; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251110 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251111; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251111 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251112; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251112 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251113; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251113 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251114; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251114 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251115; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251115 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251116; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251116 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251117; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251117 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251118; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251118 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251119; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251119 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251120; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251120 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251121; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251121 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251122; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251122 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251123; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251123 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251124; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251124 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251125; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251125 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251126; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251126 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251127; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251127 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251128; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251128 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251129; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251129 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251130; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251130 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251201; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251201 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251202; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251202 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251203; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251203 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251204; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251204 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251205; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251205 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251206; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251206 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251207; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251207 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251208; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251208 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251209; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251209 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251210; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251210 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251211; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251211 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251212; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251212 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251213; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251213 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_heartbeats_20251214; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_heartbeats_20251214 (
    hb_id bigint DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass) NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    ip character varying,
    status character varying DEFAULT 'ok'::character varying NOT NULL,
    battery_pct integer,
    plugged boolean,
    temp_c integer,
    network_type character varying,
    signal_dbm integer,
    uptime_s integer,
    ram_used_mb integer,
    unity_pkg_version character varying,
    unity_running boolean,
    agent_version character varying
);


--
-- Name: device_last_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_last_status (
    device_id character varying NOT NULL,
    last_ts timestamp without time zone NOT NULL,
    battery_pct integer,
    network_type character varying,
    unity_running boolean,
    signal_dbm integer,
    agent_version character varying,
    ip character varying,
    status character varying NOT NULL,
    service_up boolean,
    monitored_foreground_recent_s integer,
    monitored_package character varying(255),
    monitored_threshold_min integer,
    ssid character varying
);


--
-- Name: device_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_metrics (
    id bigint NOT NULL,
    device_id character varying NOT NULL,
    ts timestamp without time zone NOT NULL,
    battery_pct integer,
    charging boolean,
    network_type character varying,
    signal_dbm integer,
    uptime_ms bigint,
    app_version character varying,
    source character varying NOT NULL
);


--
-- Name: device_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.device_metrics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: device_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.device_metrics_id_seq OWNED BY public.device_metrics.id;


--
-- Name: device_selections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.device_selections (
    selection_id character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    filter_json text,
    total_count integer NOT NULL,
    device_ids_json text NOT NULL,
    created_by character varying
);


--
-- Name: devices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.devices (
    id character varying(100) NOT NULL,
    alias character varying(255) NOT NULL,
    app_version character varying(50),
    token_hash character varying(255) NOT NULL,
    token_id character varying(100),
    created_at timestamp without time zone NOT NULL,
    last_seen timestamp without time zone NOT NULL,
    last_status text,
    last_alert_state text,
    fcm_token character varying(500),
    last_ping_sent timestamp without time zone,
    last_ping_response timestamp without time zone,
    ping_request_id character varying(100),
    model character varying(100),
    manufacturer character varying(100),
    android_version character varying(50),
    sdk_int integer,
    build_id character varying(100),
    is_device_owner boolean,
    clipboard_content text,
    clipboard_updated_at timestamp without time zone,
    monitored_package character varying(255) NOT NULL,
    monitored_app_name character varying(100) NOT NULL,
    auto_relaunch_enabled boolean NOT NULL,
    token_revoked_at timestamp with time zone,
    monitored_threshold_min integer DEFAULT 10 NOT NULL,
    monitor_enabled boolean DEFAULT true NOT NULL,
    monitoring_use_defaults boolean DEFAULT true NOT NULL,
    last_ping_at timestamp without time zone,
    last_ring_at timestamp without time zone,
    ringing_until timestamp without time zone
);


--
-- Name: discord_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_settings (
    id integer NOT NULL,
    enabled boolean NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: discord_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.discord_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: discord_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.discord_settings_id_seq OWNED BY public.discord_settings.id;


--
-- Name: enrollment_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enrollment_events (
    id integer NOT NULL,
    event_type character varying NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    token_id character varying,
    alias character varying,
    device_serial character varying,
    device_id character varying,
    request_id character varying,
    build_id character varying,
    ip_address character varying,
    details text
);


--
-- Name: enrollment_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.enrollment_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enrollment_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.enrollment_events_id_seq OWNED BY public.enrollment_events.id;


--
-- Name: fcm_dispatches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.fcm_dispatches (
    request_id character varying NOT NULL,
    device_id character varying NOT NULL,
    action character varying NOT NULL,
    payload_hash character varying,
    sent_at timestamp without time zone NOT NULL,
    latency_ms integer,
    fcm_message_id character varying,
    http_code integer,
    fcm_status character varying NOT NULL,
    error_msg text,
    response_json text,
    retries integer NOT NULL,
    completed_at timestamp without time zone,
    result character varying,
    result_message text
);


--
-- Name: hb_partitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hb_partitions (
    partition_name character varying NOT NULL,
    range_start timestamp without time zone NOT NULL,
    range_end timestamp without time zone NOT NULL,
    state character varying NOT NULL,
    row_count bigint,
    bytes_size bigint,
    checksum_sha256 character varying,
    archive_url text,
    created_at timestamp without time zone NOT NULL,
    archived_at timestamp without time zone,
    dropped_at timestamp without time zone
);


--
-- Name: monitoring_defaults; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monitoring_defaults (
    id integer NOT NULL,
    enabled boolean NOT NULL,
    package character varying NOT NULL,
    alias character varying NOT NULL,
    threshold_min integer NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: monitoring_defaults_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.monitoring_defaults_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: monitoring_defaults_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.monitoring_defaults_id_seq OWNED BY public.monitoring_defaults.id;


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    id integer NOT NULL,
    user_id integer NOT NULL,
    token character varying(255) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    used boolean NOT NULL,
    used_at timestamp without time zone,
    ip_address character varying(45)
);


--
-- Name: password_reset_tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.password_reset_tokens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: password_reset_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.password_reset_tokens_id_seq OWNED BY public.password_reset_tokens.id;


--
-- Name: remote_exec; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.remote_exec (
    id character varying NOT NULL,
    mode character varying NOT NULL,
    raw_request jsonb NOT NULL,
    targets jsonb NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by character varying,
    created_by_ip character varying,
    payload_hash character varying(64),
    total_targets integer NOT NULL,
    sent_count integer NOT NULL,
    acked_count integer NOT NULL,
    error_count integer NOT NULL,
    status character varying NOT NULL,
    completed_at timestamp without time zone
);


--
-- Name: remote_exec_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.remote_exec_results (
    id bigint NOT NULL,
    exec_id character varying NOT NULL,
    device_id character varying NOT NULL,
    alias character varying,
    correlation_id character varying NOT NULL,
    status character varying NOT NULL,
    exit_code integer,
    output_preview text,
    error text,
    sent_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: remote_exec_results_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.remote_exec_results_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: remote_exec_results_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.remote_exec_results_id_seq OWNED BY public.remote_exec_results.id;


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    id character varying NOT NULL,
    user_id integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(100) NOT NULL,
    email character varying(255),
    password_hash character varying(255) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: wifi_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wifi_settings (
    id integer NOT NULL,
    ssid character varying NOT NULL,
    password character varying NOT NULL,
    security_type character varying NOT NULL,
    enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying
);


--
-- Name: wifi_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wifi_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wifi_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wifi_settings_id_seq OWNED BY public.wifi_settings.id;


--
-- Name: device_heartbeats_20251022; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251022 FOR VALUES FROM ('2025-10-22 00:00:00') TO ('2025-10-23 00:00:00');


--
-- Name: device_heartbeats_20251023; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251023 FOR VALUES FROM ('2025-10-23 00:00:00') TO ('2025-10-24 00:00:00');


--
-- Name: device_heartbeats_20251024; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251024 FOR VALUES FROM ('2025-10-24 00:00:00') TO ('2025-10-25 00:00:00');


--
-- Name: device_heartbeats_20251025; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251025 FOR VALUES FROM ('2025-10-25 00:00:00') TO ('2025-10-26 00:00:00');


--
-- Name: device_heartbeats_20251026; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251026 FOR VALUES FROM ('2025-10-26 00:00:00') TO ('2025-10-27 00:00:00');


--
-- Name: device_heartbeats_20251027; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251027 FOR VALUES FROM ('2025-10-27 00:00:00') TO ('2025-10-28 00:00:00');


--
-- Name: device_heartbeats_20251028; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251028 FOR VALUES FROM ('2025-10-28 00:00:00') TO ('2025-10-29 00:00:00');


--
-- Name: device_heartbeats_20251029; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251029 FOR VALUES FROM ('2025-10-29 00:00:00') TO ('2025-10-30 00:00:00');


--
-- Name: device_heartbeats_20251030; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251030 FOR VALUES FROM ('2025-10-30 00:00:00') TO ('2025-10-31 00:00:00');


--
-- Name: device_heartbeats_20251031; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251031 FOR VALUES FROM ('2025-10-31 00:00:00') TO ('2025-11-01 00:00:00');


--
-- Name: device_heartbeats_20251101; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251101 FOR VALUES FROM ('2025-11-01 00:00:00') TO ('2025-11-02 00:00:00');


--
-- Name: device_heartbeats_20251102; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251102 FOR VALUES FROM ('2025-11-02 00:00:00') TO ('2025-11-03 00:00:00');


--
-- Name: device_heartbeats_20251103; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251103 FOR VALUES FROM ('2025-11-03 00:00:00') TO ('2025-11-04 00:00:00');


--
-- Name: device_heartbeats_20251104; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251104 FOR VALUES FROM ('2025-11-04 00:00:00') TO ('2025-11-05 00:00:00');


--
-- Name: device_heartbeats_20251105; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251105 FOR VALUES FROM ('2025-11-05 00:00:00') TO ('2025-11-06 00:00:00');


--
-- Name: device_heartbeats_20251106; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251106 FOR VALUES FROM ('2025-11-06 00:00:00') TO ('2025-11-07 00:00:00');


--
-- Name: device_heartbeats_20251107; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251107 FOR VALUES FROM ('2025-11-07 00:00:00') TO ('2025-11-08 00:00:00');


--
-- Name: device_heartbeats_20251108; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251108 FOR VALUES FROM ('2025-11-08 00:00:00') TO ('2025-11-09 00:00:00');


--
-- Name: device_heartbeats_20251109; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251109 FOR VALUES FROM ('2025-11-09 00:00:00') TO ('2025-11-10 00:00:00');


--
-- Name: device_heartbeats_20251110; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251110 FOR VALUES FROM ('2025-11-10 00:00:00') TO ('2025-11-11 00:00:00');


--
-- Name: device_heartbeats_20251111; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251111 FOR VALUES FROM ('2025-11-11 00:00:00') TO ('2025-11-12 00:00:00');


--
-- Name: device_heartbeats_20251112; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251112 FOR VALUES FROM ('2025-11-12 00:00:00') TO ('2025-11-13 00:00:00');


--
-- Name: device_heartbeats_20251113; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251113 FOR VALUES FROM ('2025-11-13 00:00:00') TO ('2025-11-14 00:00:00');


--
-- Name: device_heartbeats_20251114; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251114 FOR VALUES FROM ('2025-11-14 00:00:00') TO ('2025-11-15 00:00:00');


--
-- Name: device_heartbeats_20251115; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251115 FOR VALUES FROM ('2025-11-15 00:00:00') TO ('2025-11-16 00:00:00');


--
-- Name: device_heartbeats_20251116; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251116 FOR VALUES FROM ('2025-11-16 00:00:00') TO ('2025-11-17 00:00:00');


--
-- Name: device_heartbeats_20251117; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251117 FOR VALUES FROM ('2025-11-17 00:00:00') TO ('2025-11-18 00:00:00');


--
-- Name: device_heartbeats_20251118; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251118 FOR VALUES FROM ('2025-11-18 00:00:00') TO ('2025-11-19 00:00:00');


--
-- Name: device_heartbeats_20251119; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251119 FOR VALUES FROM ('2025-11-19 00:00:00') TO ('2025-11-20 00:00:00');


--
-- Name: device_heartbeats_20251120; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251120 FOR VALUES FROM ('2025-11-20 00:00:00') TO ('2025-11-21 00:00:00');


--
-- Name: device_heartbeats_20251121; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251121 FOR VALUES FROM ('2025-11-21 00:00:00') TO ('2025-11-22 00:00:00');


--
-- Name: device_heartbeats_20251122; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251122 FOR VALUES FROM ('2025-11-22 00:00:00') TO ('2025-11-23 00:00:00');


--
-- Name: device_heartbeats_20251123; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251123 FOR VALUES FROM ('2025-11-23 00:00:00') TO ('2025-11-24 00:00:00');


--
-- Name: device_heartbeats_20251124; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251124 FOR VALUES FROM ('2025-11-24 00:00:00') TO ('2025-11-25 00:00:00');


--
-- Name: device_heartbeats_20251125; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251125 FOR VALUES FROM ('2025-11-25 00:00:00') TO ('2025-11-26 00:00:00');


--
-- Name: device_heartbeats_20251126; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251126 FOR VALUES FROM ('2025-11-26 00:00:00') TO ('2025-11-27 00:00:00');


--
-- Name: device_heartbeats_20251127; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251127 FOR VALUES FROM ('2025-11-27 00:00:00') TO ('2025-11-28 00:00:00');


--
-- Name: device_heartbeats_20251128; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251128 FOR VALUES FROM ('2025-11-28 00:00:00') TO ('2025-11-29 00:00:00');


--
-- Name: device_heartbeats_20251129; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251129 FOR VALUES FROM ('2025-11-29 00:00:00') TO ('2025-11-30 00:00:00');


--
-- Name: device_heartbeats_20251130; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251130 FOR VALUES FROM ('2025-11-30 00:00:00') TO ('2025-12-01 00:00:00');


--
-- Name: device_heartbeats_20251201; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251201 FOR VALUES FROM ('2025-12-01 00:00:00') TO ('2025-12-02 00:00:00');


--
-- Name: device_heartbeats_20251202; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251202 FOR VALUES FROM ('2025-12-02 00:00:00') TO ('2025-12-03 00:00:00');


--
-- Name: device_heartbeats_20251203; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251203 FOR VALUES FROM ('2025-12-03 00:00:00') TO ('2025-12-04 00:00:00');


--
-- Name: device_heartbeats_20251204; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251204 FOR VALUES FROM ('2025-12-04 00:00:00') TO ('2025-12-05 00:00:00');


--
-- Name: device_heartbeats_20251205; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251205 FOR VALUES FROM ('2025-12-05 00:00:00') TO ('2025-12-06 00:00:00');


--
-- Name: device_heartbeats_20251206; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251206 FOR VALUES FROM ('2025-12-06 00:00:00') TO ('2025-12-07 00:00:00');


--
-- Name: device_heartbeats_20251207; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251207 FOR VALUES FROM ('2025-12-07 00:00:00') TO ('2025-12-08 00:00:00');


--
-- Name: device_heartbeats_20251208; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251208 FOR VALUES FROM ('2025-12-08 00:00:00') TO ('2025-12-09 00:00:00');


--
-- Name: device_heartbeats_20251209; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251209 FOR VALUES FROM ('2025-12-09 00:00:00') TO ('2025-12-10 00:00:00');


--
-- Name: device_heartbeats_20251210; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251210 FOR VALUES FROM ('2025-12-10 00:00:00') TO ('2025-12-11 00:00:00');


--
-- Name: device_heartbeats_20251211; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251211 FOR VALUES FROM ('2025-12-11 00:00:00') TO ('2025-12-12 00:00:00');


--
-- Name: device_heartbeats_20251212; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251212 FOR VALUES FROM ('2025-12-12 00:00:00') TO ('2025-12-13 00:00:00');


--
-- Name: device_heartbeats_20251213; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251213 FOR VALUES FROM ('2025-12-13 00:00:00') TO ('2025-12-14 00:00:00');


--
-- Name: device_heartbeats_20251214; Type: TABLE ATTACH; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ATTACH PARTITION public.device_heartbeats_20251214 FOR VALUES FROM ('2025-12-14 00:00:00') TO ('2025-12-15 00:00:00');


--
-- Name: alert_states id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_states ALTER COLUMN id SET DEFAULT nextval('public.alert_states_id_seq'::regclass);


--
-- Name: apk_download_events event_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_download_events ALTER COLUMN event_id SET DEFAULT nextval('public.apk_download_events_event_id_seq'::regclass);


--
-- Name: apk_installations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_installations ALTER COLUMN id SET DEFAULT nextval('public.apk_installations_id_seq'::regclass);


--
-- Name: apk_versions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_versions ALTER COLUMN id SET DEFAULT nextval('public.apk_versions_id_seq'::regclass);


--
-- Name: auto_relaunch_defaults id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auto_relaunch_defaults ALTER COLUMN id SET DEFAULT nextval('public.auto_relaunch_defaults_id_seq'::regclass);


--
-- Name: battery_whitelist id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battery_whitelist ALTER COLUMN id SET DEFAULT nextval('public.battery_whitelist_id_seq'::regclass);


--
-- Name: bloatware_packages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bloatware_packages ALTER COLUMN id SET DEFAULT nextval('public.bloatware_packages_id_seq'::regclass);


--
-- Name: command_results id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_results ALTER COLUMN id SET DEFAULT nextval('public.command_results_id_seq'::regclass);


--
-- Name: commands id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands ALTER COLUMN id SET DEFAULT nextval('public.commands_id_seq'::regclass);


--
-- Name: device_commands id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_commands ALTER COLUMN id SET DEFAULT nextval('public.device_commands_id_seq'::regclass);


--
-- Name: device_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_events ALTER COLUMN id SET DEFAULT nextval('public.device_events_id_seq'::regclass);


--
-- Name: device_heartbeats hb_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats ALTER COLUMN hb_id SET DEFAULT nextval('public.device_heartbeats_hb_id_seq1'::regclass);


--
-- Name: device_metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_metrics ALTER COLUMN id SET DEFAULT nextval('public.device_metrics_id_seq'::regclass);


--
-- Name: discord_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_settings ALTER COLUMN id SET DEFAULT nextval('public.discord_settings_id_seq'::regclass);


--
-- Name: enrollment_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollment_events ALTER COLUMN id SET DEFAULT nextval('public.enrollment_events_id_seq'::regclass);


--
-- Name: monitoring_defaults id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_defaults ALTER COLUMN id SET DEFAULT nextval('public.monitoring_defaults_id_seq'::regclass);


--
-- Name: password_reset_tokens id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens ALTER COLUMN id SET DEFAULT nextval('public.password_reset_tokens_id_seq'::regclass);


--
-- Name: remote_exec_results id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remote_exec_results ALTER COLUMN id SET DEFAULT nextval('public.remote_exec_results_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: wifi_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wifi_settings ALTER COLUMN id SET DEFAULT nextval('public.wifi_settings_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: alert_states alert_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_states
    ADD CONSTRAINT alert_states_pkey PRIMARY KEY (id);


--
-- Name: apk_deployment_stats apk_deployment_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_deployment_stats
    ADD CONSTRAINT apk_deployment_stats_pkey PRIMARY KEY (build_id);


--
-- Name: apk_download_events apk_download_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_download_events
    ADD CONSTRAINT apk_download_events_pkey PRIMARY KEY (event_id);


--
-- Name: apk_installations apk_installations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_installations
    ADD CONSTRAINT apk_installations_pkey PRIMARY KEY (id);


--
-- Name: apk_versions apk_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_versions
    ADD CONSTRAINT apk_versions_pkey PRIMARY KEY (id);


--
-- Name: auto_relaunch_defaults auto_relaunch_defaults_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auto_relaunch_defaults
    ADD CONSTRAINT auto_relaunch_defaults_pkey PRIMARY KEY (id);


--
-- Name: battery_whitelist battery_whitelist_package_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battery_whitelist
    ADD CONSTRAINT battery_whitelist_package_name_key UNIQUE (package_name);


--
-- Name: battery_whitelist battery_whitelist_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.battery_whitelist
    ADD CONSTRAINT battery_whitelist_pkey PRIMARY KEY (id);


--
-- Name: bloatware_packages bloatware_packages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bloatware_packages
    ADD CONSTRAINT bloatware_packages_pkey PRIMARY KEY (id);


--
-- Name: bulk_commands bulk_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bulk_commands
    ADD CONSTRAINT bulk_commands_pkey PRIMARY KEY (id);


--
-- Name: command_results command_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_results
    ADD CONSTRAINT command_results_pkey PRIMARY KEY (id);


--
-- Name: commands commands_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands
    ADD CONSTRAINT commands_pkey PRIMARY KEY (id);


--
-- Name: device_commands device_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_commands
    ADD CONSTRAINT device_commands_pkey PRIMARY KEY (id);


--
-- Name: device_events device_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_events
    ADD CONSTRAINT device_events_pkey PRIMARY KEY (id);


--
-- Name: device_heartbeats device_heartbeats_pkey1; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats
    ADD CONSTRAINT device_heartbeats_pkey1 PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251022 device_heartbeats_20251022_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251022
    ADD CONSTRAINT device_heartbeats_20251022_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251023 device_heartbeats_20251023_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251023
    ADD CONSTRAINT device_heartbeats_20251023_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251024 device_heartbeats_20251024_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251024
    ADD CONSTRAINT device_heartbeats_20251024_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251025 device_heartbeats_20251025_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251025
    ADD CONSTRAINT device_heartbeats_20251025_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251026 device_heartbeats_20251026_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251026
    ADD CONSTRAINT device_heartbeats_20251026_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251027 device_heartbeats_20251027_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251027
    ADD CONSTRAINT device_heartbeats_20251027_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251028 device_heartbeats_20251028_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251028
    ADD CONSTRAINT device_heartbeats_20251028_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251029 device_heartbeats_20251029_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251029
    ADD CONSTRAINT device_heartbeats_20251029_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251030 device_heartbeats_20251030_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251030
    ADD CONSTRAINT device_heartbeats_20251030_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251031 device_heartbeats_20251031_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251031
    ADD CONSTRAINT device_heartbeats_20251031_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251101 device_heartbeats_20251101_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251101
    ADD CONSTRAINT device_heartbeats_20251101_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251102 device_heartbeats_20251102_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251102
    ADD CONSTRAINT device_heartbeats_20251102_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251103 device_heartbeats_20251103_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251103
    ADD CONSTRAINT device_heartbeats_20251103_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251104 device_heartbeats_20251104_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251104
    ADD CONSTRAINT device_heartbeats_20251104_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251105 device_heartbeats_20251105_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251105
    ADD CONSTRAINT device_heartbeats_20251105_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251106 device_heartbeats_20251106_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251106
    ADD CONSTRAINT device_heartbeats_20251106_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251107 device_heartbeats_20251107_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251107
    ADD CONSTRAINT device_heartbeats_20251107_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251108 device_heartbeats_20251108_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251108
    ADD CONSTRAINT device_heartbeats_20251108_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251109 device_heartbeats_20251109_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251109
    ADD CONSTRAINT device_heartbeats_20251109_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251110 device_heartbeats_20251110_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251110
    ADD CONSTRAINT device_heartbeats_20251110_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251111 device_heartbeats_20251111_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251111
    ADD CONSTRAINT device_heartbeats_20251111_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251112 device_heartbeats_20251112_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251112
    ADD CONSTRAINT device_heartbeats_20251112_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251113 device_heartbeats_20251113_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251113
    ADD CONSTRAINT device_heartbeats_20251113_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251114 device_heartbeats_20251114_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251114
    ADD CONSTRAINT device_heartbeats_20251114_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251115 device_heartbeats_20251115_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251115
    ADD CONSTRAINT device_heartbeats_20251115_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251116 device_heartbeats_20251116_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251116
    ADD CONSTRAINT device_heartbeats_20251116_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251117 device_heartbeats_20251117_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251117
    ADD CONSTRAINT device_heartbeats_20251117_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251118 device_heartbeats_20251118_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251118
    ADD CONSTRAINT device_heartbeats_20251118_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251119 device_heartbeats_20251119_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251119
    ADD CONSTRAINT device_heartbeats_20251119_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251120 device_heartbeats_20251120_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251120
    ADD CONSTRAINT device_heartbeats_20251120_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251121 device_heartbeats_20251121_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251121
    ADD CONSTRAINT device_heartbeats_20251121_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251122 device_heartbeats_20251122_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251122
    ADD CONSTRAINT device_heartbeats_20251122_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251123 device_heartbeats_20251123_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251123
    ADD CONSTRAINT device_heartbeats_20251123_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251124 device_heartbeats_20251124_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251124
    ADD CONSTRAINT device_heartbeats_20251124_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251125 device_heartbeats_20251125_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251125
    ADD CONSTRAINT device_heartbeats_20251125_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251126 device_heartbeats_20251126_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251126
    ADD CONSTRAINT device_heartbeats_20251126_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251127 device_heartbeats_20251127_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251127
    ADD CONSTRAINT device_heartbeats_20251127_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251128 device_heartbeats_20251128_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251128
    ADD CONSTRAINT device_heartbeats_20251128_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251129 device_heartbeats_20251129_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251129
    ADD CONSTRAINT device_heartbeats_20251129_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251130 device_heartbeats_20251130_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251130
    ADD CONSTRAINT device_heartbeats_20251130_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251201 device_heartbeats_20251201_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251201
    ADD CONSTRAINT device_heartbeats_20251201_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251202 device_heartbeats_20251202_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251202
    ADD CONSTRAINT device_heartbeats_20251202_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251203 device_heartbeats_20251203_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251203
    ADD CONSTRAINT device_heartbeats_20251203_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251204 device_heartbeats_20251204_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251204
    ADD CONSTRAINT device_heartbeats_20251204_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251205 device_heartbeats_20251205_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251205
    ADD CONSTRAINT device_heartbeats_20251205_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251206 device_heartbeats_20251206_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251206
    ADD CONSTRAINT device_heartbeats_20251206_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251207 device_heartbeats_20251207_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251207
    ADD CONSTRAINT device_heartbeats_20251207_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251208 device_heartbeats_20251208_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251208
    ADD CONSTRAINT device_heartbeats_20251208_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251209 device_heartbeats_20251209_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251209
    ADD CONSTRAINT device_heartbeats_20251209_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251210 device_heartbeats_20251210_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251210
    ADD CONSTRAINT device_heartbeats_20251210_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251211 device_heartbeats_20251211_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251211
    ADD CONSTRAINT device_heartbeats_20251211_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251212 device_heartbeats_20251212_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251212
    ADD CONSTRAINT device_heartbeats_20251212_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251213 device_heartbeats_20251213_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251213
    ADD CONSTRAINT device_heartbeats_20251213_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_heartbeats_20251214 device_heartbeats_20251214_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_heartbeats_20251214
    ADD CONSTRAINT device_heartbeats_20251214_pkey PRIMARY KEY (device_id, ts, hb_id);


--
-- Name: device_last_status device_last_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_last_status
    ADD CONSTRAINT device_last_status_pkey PRIMARY KEY (device_id);


--
-- Name: device_metrics device_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_metrics
    ADD CONSTRAINT device_metrics_pkey PRIMARY KEY (id);


--
-- Name: device_selections device_selections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_selections
    ADD CONSTRAINT device_selections_pkey PRIMARY KEY (selection_id);


--
-- Name: devices devices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_pkey PRIMARY KEY (id);


--
-- Name: discord_settings discord_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_settings
    ADD CONSTRAINT discord_settings_pkey PRIMARY KEY (id);


--
-- Name: enrollment_events enrollment_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollment_events
    ADD CONSTRAINT enrollment_events_pkey PRIMARY KEY (id);


--
-- Name: fcm_dispatches fcm_dispatches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fcm_dispatches
    ADD CONSTRAINT fcm_dispatches_pkey PRIMARY KEY (request_id);


--
-- Name: hb_partitions hb_partitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hb_partitions
    ADD CONSTRAINT hb_partitions_pkey PRIMARY KEY (partition_name);


--
-- Name: monitoring_defaults monitoring_defaults_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monitoring_defaults
    ADD CONSTRAINT monitoring_defaults_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);


--
-- Name: remote_exec remote_exec_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remote_exec
    ADD CONSTRAINT remote_exec_pkey PRIMARY KEY (id);


--
-- Name: remote_exec_results remote_exec_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remote_exec_results
    ADD CONSTRAINT remote_exec_results_pkey PRIMARY KEY (id);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: command_results uq_command_device; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_results
    ADD CONSTRAINT uq_command_device UNIQUE (command_id, device_id);


--
-- Name: alert_states uq_device_condition; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_states
    ADD CONSTRAINT uq_device_condition UNIQUE (device_id, condition);


--
-- Name: remote_exec_results uq_exec_device; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remote_exec_results
    ADD CONSTRAINT uq_exec_device UNIQUE (exec_id, device_id);


--
-- Name: apk_versions uq_package_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_versions
    ADD CONSTRAINT uq_package_version UNIQUE (package_name, version_code);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: wifi_settings wifi_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wifi_settings
    ADD CONSTRAINT wifi_settings_pkey PRIMARY KEY (id);


--
-- Name: apk_versions_is_current_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX apk_versions_is_current_idx ON public.apk_versions USING btree (is_current);


--
-- Name: idx_alert_cooldown; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_cooldown ON public.alert_states USING btree (cooldown_until);


--
-- Name: idx_alert_device_condition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_device_condition ON public.alert_states USING btree (device_id, condition);


--
-- Name: idx_apk_build_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_apk_build_type ON public.apk_versions USING btree (version_code, build_type);


--
-- Name: idx_apk_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_apk_current ON public.apk_versions USING btree (is_current, package_name);


--
-- Name: idx_apk_download_build_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_apk_download_build_ts ON public.apk_download_events USING btree (build_id, ts);


--
-- Name: idx_apk_download_token_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_apk_download_token_ts ON public.apk_download_events USING btree (token_id, ts);


--
-- Name: idx_apk_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_apk_sha256 ON public.apk_versions USING btree (sha256);


--
-- Name: idx_apk_version_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_apk_version_lookup ON public.apk_versions USING btree (package_name, version_code);


--
-- Name: idx_auto_relaunch_defaults_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_auto_relaunch_defaults_updated ON public.auto_relaunch_defaults USING btree (updated_at);


--
-- Name: idx_bloatware_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bloatware_enabled ON public.bloatware_packages USING btree (enabled);


--
-- Name: idx_bulk_command_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bulk_command_status ON public.bulk_commands USING btree (status, created_at);


--
-- Name: idx_bulk_command_type_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bulk_command_type_created ON public.bulk_commands USING btree (type, created_at);


--
-- Name: idx_command_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_created ON public.commands USING btree (created_at);


--
-- Name: idx_command_result_command; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_result_command ON public.command_results USING btree (command_id, status);


--
-- Name: idx_command_result_correlation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_result_correlation ON public.command_results USING btree (correlation_id);


--
-- Name: idx_command_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_command_status ON public.commands USING btree (device_id, status);


--
-- Name: idx_deployment_stats_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_deployment_stats_updated ON public.apk_deployment_stats USING btree (last_updated);


--
-- Name: idx_device_command_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_command_status ON public.device_commands USING btree (device_id, status);


--
-- Name: idx_device_command_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_command_type ON public.device_commands USING btree (type, created_at);


--
-- Name: idx_device_event_query; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_event_query ON public.device_events USING btree (device_id, "timestamp");


--
-- Name: idx_device_heartbeats_20251022_dedupe; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_device_heartbeats_20251022_dedupe ON public.device_heartbeats_20251022 USING btree (device_id, date_trunc('minute'::text, ts), ((((EXTRACT(epoch FROM ts))::bigint / 10) % (6)::bigint)));


--
-- Name: idx_device_heartbeats_20251022_device_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_heartbeats_20251022_device_ts ON public.device_heartbeats_20251022 USING btree (device_id, ts DESC);


--
-- Name: idx_device_heartbeats_20251023_dedupe; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_device_heartbeats_20251023_dedupe ON public.device_heartbeats_20251023 USING btree (device_id, date_trunc('minute'::text, ts), ((((EXTRACT(epoch FROM ts))::bigint / 10) % (6)::bigint)));


--
-- Name: idx_device_heartbeats_20251023_device_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_heartbeats_20251023_device_ts ON public.device_heartbeats_20251023 USING btree (device_id, ts DESC);


--
-- Name: idx_device_heartbeats_20251024_dedupe; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_device_heartbeats_20251024_dedupe ON public.device_heartbeats_20251024 USING btree (device_id, date_trunc('minute'::text, ts), ((((EXTRACT(epoch FROM ts))::bigint / 10) % (6)::bigint)));


--
-- Name: idx_device_heartbeats_20251024_device_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_heartbeats_20251024_device_ts ON public.device_heartbeats_20251024 USING btree (device_id, ts DESC);


--
-- Name: idx_device_metric_device_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_metric_device_ts ON public.device_metrics USING btree (device_id, ts);


--
-- Name: idx_device_metric_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_metric_source ON public.device_metrics USING btree (source, ts);


--
-- Name: idx_device_monitoring; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_monitoring ON public.devices USING btree (monitor_enabled, monitored_package);


--
-- Name: idx_device_ringing; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_ringing ON public.devices USING btree (ringing_until);


--
-- Name: idx_device_selections_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_selections_created_at ON public.device_selections USING btree (created_at);


--
-- Name: idx_device_status_query; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_status_query ON public.devices USING btree (last_seen);


--
-- Name: idx_device_token_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_device_token_lookup ON public.devices USING btree (token_id);


--
-- Name: idx_discord_settings_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_settings_updated ON public.discord_settings USING btree (updated_at);


--
-- Name: idx_enrollment_event_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrollment_event_token ON public.enrollment_events USING btree (token_id, "timestamp");


--
-- Name: idx_enrollment_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enrollment_event_type ON public.enrollment_events USING btree (event_type, "timestamp");


--
-- Name: idx_fcm_action_sent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fcm_action_sent ON public.fcm_dispatches USING btree (action, sent_at);


--
-- Name: idx_fcm_device_sent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fcm_device_sent ON public.fcm_dispatches USING btree (device_id, sent_at);


--
-- Name: idx_hb_partition_range; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hb_partition_range ON public.hb_partitions USING btree (range_start, range_end);


--
-- Name: idx_hb_partition_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_hb_partition_state ON public.hb_partitions USING btree (state);


--
-- Name: idx_installation_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_installation_status ON public.apk_installations USING btree (device_id, status);


--
-- Name: idx_installation_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_installation_time ON public.apk_installations USING btree (initiated_at);


--
-- Name: idx_installation_version_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_installation_version_status ON public.apk_installations USING btree (apk_version_id, status);


--
-- Name: idx_last_status_offline_query; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_last_status_offline_query ON public.device_last_status USING btree (last_ts, status);


--
-- Name: idx_last_status_service_down; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_last_status_service_down ON public.device_last_status USING btree (service_up, last_ts);


--
-- Name: idx_last_status_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_last_status_ts ON public.device_last_status USING btree (last_ts);


--
-- Name: idx_last_status_unity_down; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_last_status_unity_down ON public.device_last_status USING btree (unity_running, last_ts);


--
-- Name: idx_monitoring_defaults_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_monitoring_defaults_updated ON public.monitoring_defaults USING btree (updated_at);


--
-- Name: idx_password_reset_token_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_password_reset_token_lookup ON public.password_reset_tokens USING btree (token, expires_at);


--
-- Name: idx_password_reset_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_password_reset_user ON public.password_reset_tokens USING btree (user_id, created_at);


--
-- Name: idx_remote_exec_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_remote_exec_created_by ON public.remote_exec USING btree (created_by, created_at);


--
-- Name: idx_remote_exec_mode_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_remote_exec_mode_created ON public.remote_exec USING btree (mode, created_at);


--
-- Name: idx_remote_exec_result_correlation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_remote_exec_result_correlation ON public.remote_exec_results USING btree (correlation_id);


--
-- Name: idx_remote_exec_result_device; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_remote_exec_result_device ON public.remote_exec_results USING btree (device_id, sent_at);


--
-- Name: idx_remote_exec_result_exec; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_remote_exec_result_exec ON public.remote_exec_results USING btree (exec_id, status);


--
-- Name: idx_remote_exec_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_remote_exec_status ON public.remote_exec USING btree (status, created_at);


--
-- Name: idx_selection_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_selection_created ON public.device_selections USING btree (created_at);


--
-- Name: idx_selection_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_selection_expires ON public.device_selections USING btree (expires_at);


--
-- Name: idx_whitelist_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_whitelist_enabled ON public.battery_whitelist USING btree (enabled);


--
-- Name: idx_wifi_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wifi_enabled ON public.wifi_settings USING btree (enabled);


--
-- Name: ix_alert_states_cooldown_until; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_states_cooldown_until ON public.alert_states USING btree (cooldown_until);


--
-- Name: ix_alert_states_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_states_device_id ON public.alert_states USING btree (device_id);


--
-- Name: ix_apk_download_events_build_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_apk_download_events_build_id ON public.apk_download_events USING btree (build_id);


--
-- Name: ix_apk_download_events_token_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_apk_download_events_token_id ON public.apk_download_events USING btree (token_id);


--
-- Name: ix_apk_download_events_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_apk_download_events_ts ON public.apk_download_events USING btree (ts);


--
-- Name: ix_apk_installations_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_apk_installations_device_id ON public.apk_installations USING btree (device_id);


--
-- Name: ix_bloatware_packages_package_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_bloatware_packages_package_name ON public.bloatware_packages USING btree (package_name);


--
-- Name: ix_bulk_commands_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bulk_commands_created_at ON public.bulk_commands USING btree (created_at);


--
-- Name: ix_bulk_commands_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bulk_commands_status ON public.bulk_commands USING btree (status);


--
-- Name: ix_bulk_commands_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_bulk_commands_type ON public.bulk_commands USING btree (type);


--
-- Name: ix_command_results_command_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_command_results_command_id ON public.command_results USING btree (command_id);


--
-- Name: ix_command_results_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_command_results_correlation_id ON public.command_results USING btree (correlation_id);


--
-- Name: ix_command_results_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_command_results_device_id ON public.command_results USING btree (device_id);


--
-- Name: ix_commands_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commands_device_id ON public.commands USING btree (device_id);


--
-- Name: ix_commands_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_commands_request_id ON public.commands USING btree (request_id);


--
-- Name: ix_device_commands_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_device_commands_correlation_id ON public.device_commands USING btree (correlation_id);


--
-- Name: ix_device_commands_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_commands_created_at ON public.device_commands USING btree (created_at);


--
-- Name: ix_device_commands_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_commands_device_id ON public.device_commands USING btree (device_id);


--
-- Name: ix_device_events_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_events_device_id ON public.device_events USING btree (device_id);


--
-- Name: ix_device_events_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_events_timestamp ON public.device_events USING btree ("timestamp");


--
-- Name: ix_device_last_status_last_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_last_status_last_ts ON public.device_last_status USING btree (last_ts);


--
-- Name: ix_device_metrics_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_metrics_device_id ON public.device_metrics USING btree (device_id);


--
-- Name: ix_device_metrics_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_metrics_ts ON public.device_metrics USING btree (ts);


--
-- Name: ix_device_selections_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_selections_created_at ON public.device_selections USING btree (created_at);


--
-- Name: ix_device_selections_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_device_selections_expires_at ON public.device_selections USING btree (expires_at);


--
-- Name: ix_devices_last_seen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_devices_last_seen ON public.devices USING btree (last_seen);


--
-- Name: ix_devices_token_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_devices_token_id ON public.devices USING btree (token_id);


--
-- Name: ix_enrollment_events_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_enrollment_events_event_type ON public.enrollment_events USING btree (event_type);


--
-- Name: ix_enrollment_events_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_enrollment_events_timestamp ON public.enrollment_events USING btree ("timestamp");


--
-- Name: ix_enrollment_events_token_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_enrollment_events_token_id ON public.enrollment_events USING btree (token_id);


--
-- Name: ix_fcm_dispatches_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fcm_dispatches_device_id ON public.fcm_dispatches USING btree (device_id);


--
-- Name: ix_fcm_dispatches_fcm_message_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fcm_dispatches_fcm_message_id ON public.fcm_dispatches USING btree (fcm_message_id);


--
-- Name: ix_fcm_dispatches_sent_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_fcm_dispatches_sent_at ON public.fcm_dispatches USING btree (sent_at);


--
-- Name: ix_password_reset_tokens_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_password_reset_tokens_token ON public.password_reset_tokens USING btree (token);


--
-- Name: ix_password_reset_tokens_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_reset_tokens_user_id ON public.password_reset_tokens USING btree (user_id);


--
-- Name: ix_remote_exec_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_remote_exec_created_at ON public.remote_exec USING btree (created_at);


--
-- Name: ix_remote_exec_mode; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_remote_exec_mode ON public.remote_exec USING btree (mode);


--
-- Name: ix_remote_exec_results_correlation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_remote_exec_results_correlation_id ON public.remote_exec_results USING btree (correlation_id);


--
-- Name: ix_remote_exec_results_device_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_remote_exec_results_device_id ON public.remote_exec_results USING btree (device_id);


--
-- Name: ix_remote_exec_results_exec_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_remote_exec_results_exec_id ON public.remote_exec_results USING btree (exec_id);


--
-- Name: ix_remote_exec_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_remote_exec_status ON public.remote_exec USING btree (status);


--
-- Name: device_heartbeats_20251022_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251022_pkey;


--
-- Name: device_heartbeats_20251023_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251023_pkey;


--
-- Name: device_heartbeats_20251024_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251024_pkey;


--
-- Name: device_heartbeats_20251025_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251025_pkey;


--
-- Name: device_heartbeats_20251026_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251026_pkey;


--
-- Name: device_heartbeats_20251027_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251027_pkey;


--
-- Name: device_heartbeats_20251028_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251028_pkey;


--
-- Name: device_heartbeats_20251029_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251029_pkey;


--
-- Name: device_heartbeats_20251030_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251030_pkey;


--
-- Name: device_heartbeats_20251031_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251031_pkey;


--
-- Name: device_heartbeats_20251101_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251101_pkey;


--
-- Name: device_heartbeats_20251102_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251102_pkey;


--
-- Name: device_heartbeats_20251103_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251103_pkey;


--
-- Name: device_heartbeats_20251104_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251104_pkey;


--
-- Name: device_heartbeats_20251105_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251105_pkey;


--
-- Name: device_heartbeats_20251106_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251106_pkey;


--
-- Name: device_heartbeats_20251107_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251107_pkey;


--
-- Name: device_heartbeats_20251108_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251108_pkey;


--
-- Name: device_heartbeats_20251109_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251109_pkey;


--
-- Name: device_heartbeats_20251110_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251110_pkey;


--
-- Name: device_heartbeats_20251111_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251111_pkey;


--
-- Name: device_heartbeats_20251112_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251112_pkey;


--
-- Name: device_heartbeats_20251113_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251113_pkey;


--
-- Name: device_heartbeats_20251114_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251114_pkey;


--
-- Name: device_heartbeats_20251115_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251115_pkey;


--
-- Name: device_heartbeats_20251116_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251116_pkey;


--
-- Name: device_heartbeats_20251117_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251117_pkey;


--
-- Name: device_heartbeats_20251118_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251118_pkey;


--
-- Name: device_heartbeats_20251119_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251119_pkey;


--
-- Name: device_heartbeats_20251120_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251120_pkey;


--
-- Name: device_heartbeats_20251121_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251121_pkey;


--
-- Name: device_heartbeats_20251122_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251122_pkey;


--
-- Name: device_heartbeats_20251123_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251123_pkey;


--
-- Name: device_heartbeats_20251124_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251124_pkey;


--
-- Name: device_heartbeats_20251125_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251125_pkey;


--
-- Name: device_heartbeats_20251126_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251126_pkey;


--
-- Name: device_heartbeats_20251127_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251127_pkey;


--
-- Name: device_heartbeats_20251128_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251128_pkey;


--
-- Name: device_heartbeats_20251129_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251129_pkey;


--
-- Name: device_heartbeats_20251130_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251130_pkey;


--
-- Name: device_heartbeats_20251201_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251201_pkey;


--
-- Name: device_heartbeats_20251202_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251202_pkey;


--
-- Name: device_heartbeats_20251203_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251203_pkey;


--
-- Name: device_heartbeats_20251204_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251204_pkey;


--
-- Name: device_heartbeats_20251205_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251205_pkey;


--
-- Name: device_heartbeats_20251206_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251206_pkey;


--
-- Name: device_heartbeats_20251207_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251207_pkey;


--
-- Name: device_heartbeats_20251208_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251208_pkey;


--
-- Name: device_heartbeats_20251209_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251209_pkey;


--
-- Name: device_heartbeats_20251210_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251210_pkey;


--
-- Name: device_heartbeats_20251211_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251211_pkey;


--
-- Name: device_heartbeats_20251212_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251212_pkey;


--
-- Name: device_heartbeats_20251213_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251213_pkey;


--
-- Name: device_heartbeats_20251214_pkey; Type: INDEX ATTACH; Schema: public; Owner: -
--

ALTER INDEX public.device_heartbeats_pkey1 ATTACH PARTITION public.device_heartbeats_20251214_pkey;


--
-- Name: alert_states alert_states_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_states
    ADD CONSTRAINT alert_states_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: apk_deployment_stats apk_deployment_stats_build_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_deployment_stats
    ADD CONSTRAINT apk_deployment_stats_build_id_fkey FOREIGN KEY (build_id) REFERENCES public.apk_versions(id);


--
-- Name: apk_download_events apk_download_events_build_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_download_events
    ADD CONSTRAINT apk_download_events_build_id_fkey FOREIGN KEY (build_id) REFERENCES public.apk_versions(id);


--
-- Name: apk_installations apk_installations_apk_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_installations
    ADD CONSTRAINT apk_installations_apk_version_id_fkey FOREIGN KEY (apk_version_id) REFERENCES public.apk_versions(id);


--
-- Name: apk_installations apk_installations_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apk_installations
    ADD CONSTRAINT apk_installations_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: command_results command_results_command_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_results
    ADD CONSTRAINT command_results_command_id_fkey FOREIGN KEY (command_id) REFERENCES public.bulk_commands(id) ON DELETE CASCADE;


--
-- Name: command_results command_results_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.command_results
    ADD CONSTRAINT command_results_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: commands commands_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commands
    ADD CONSTRAINT commands_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: device_commands device_commands_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_commands
    ADD CONSTRAINT device_commands_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: device_events device_events_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_events
    ADD CONSTRAINT device_events_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: device_heartbeats device_heartbeats_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.device_heartbeats
    ADD CONSTRAINT device_heartbeats_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: device_last_status device_last_status_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_last_status
    ADD CONSTRAINT device_last_status_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: device_metrics device_metrics_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.device_metrics
    ADD CONSTRAINT device_metrics_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: fcm_dispatches fcm_dispatches_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.fcm_dispatches
    ADD CONSTRAINT fcm_dispatches_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: password_reset_tokens password_reset_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: remote_exec_results remote_exec_results_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remote_exec_results
    ADD CONSTRAINT remote_exec_results_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id) ON DELETE CASCADE;


--
-- Name: remote_exec_results remote_exec_results_exec_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.remote_exec_results
    ADD CONSTRAINT remote_exec_results_exec_id_fkey FOREIGN KEY (exec_id) REFERENCES public.remote_exec(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

