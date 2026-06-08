"""
Response Normalizer for vendor-neutral agent tooling.

Transforms provider-specific API responses into normalized schemas.
Unsupported fields are set to None rather than omitted.
Unmapped source fields are captured in providerMetadata.
"""


# --- Field mappings per provider for compute instances ---
_COMPUTE_FIELD_MAP = {
    "aws": {
        "instanceId": "InstanceId",
        "instanceType": "InstanceType",
        "state": "State.Name",
        "name": "_name_from_tags",
        "region": "Placement.AvailabilityZone",
        "launchTime": "LaunchTime",
        "nativeId": "InstanceId",
    },
    "azure": {
        "instanceId": "id",
        "instanceType": "properties.hardwareProfile.vmSize",
        "state": "properties.provisioningState",
        "name": "name",
        "region": "location",
        "launchTime": "properties.timeCreated",
        "nativeId": "id",
    },
    "gcp": {
        "instanceId": "id",
        "instanceType": "machineType",
        "state": "status",
        "name": "name",
        "region": "zone",
        "launchTime": "creationTimestamp",
        "nativeId": "selfLink",
    },
}

# --- Field mappings per provider for database instances ---
_DATABASE_FIELD_MAP = {
    "aws": {
        "instanceId": "DBInstanceIdentifier",
        "instanceType": "DBInstanceClass",
        "engine": "Engine",
        "status": "DBInstanceStatus",
        "storageSizeGB": "AllocatedStorage",
        "multiAZ": "MultiAZ",
        "nativeId": "DBInstanceArn",
    },
    "azure": {
        "instanceId": "id",
        "instanceType": "sku.name",
        "engine": "properties.version",
        "status": "properties.state",
        "storageSizeGB": "properties.storageProfile.storageMB",
        "multiAZ": "properties.highAvailability.mode",
        "nativeId": "id",
    },
    "gcp": {
        "instanceId": "name",
        "instanceType": "tier",
        "engine": "databaseVersion",
        "status": "state",
        "storageSizeGB": "settings.dataDiskSizeGb",
        "multiAZ": "settings.availabilityType",
        "nativeId": "selfLink",
    },
}

# --- Field mappings per provider for storage volumes ---
_STORAGE_FIELD_MAP = {
    "aws": {
        "volumeId": "VolumeId",
        "volumeType": "VolumeType",
        "sizeGB": "Size",
        "state": "State",
        "attached": "Attachments",
        "nativeId": "VolumeId",
    },
    "azure": {
        "volumeId": "id",
        "volumeType": "sku.name",
        "sizeGB": "properties.diskSizeGB",
        "state": "properties.diskState",
        "attached": "managedBy",
        "nativeId": "id",
    },
    "gcp": {
        "volumeId": "id",
        "volumeType": "type",
        "sizeGB": "sizeGb",
        "state": "status",
        "attached": "users",
        "nativeId": "selfLink",
    },
}


def _safe_get(data, dotted_key, default=None):
    """Safely get a nested value from a dict using dot notation."""
    if not isinstance(data, dict):
        return default
    keys = dotted_key.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def _extract_aws_instance_name(instance):
    """Extract 'Name' tag from AWS EC2 instance tags list."""
    tags = instance.get("Tags", [])
    if not isinstance(tags, list):
        return None
    for tag in tags:
        if isinstance(tag, dict) and tag.get("Key") == "Name":
            return tag.get("Value")
    return None


def _get_known_fields_for_compute(provider):
    """Return set of known source field names for a compute provider."""
    mapping = _COMPUTE_FIELD_MAP.get(provider, {})
    known = set()
    for source_key in mapping.values():
        if source_key == "_name_from_tags":
            known.add("Tags")
        else:
            known.add(source_key.split(".")[0])
    return known


def _get_known_fields_for_database(provider):
    """Return set of known source field names for a database provider."""
    mapping = _DATABASE_FIELD_MAP.get(provider, {})
    known = set()
    for source_key in mapping.values():
        known.add(source_key.split(".")[0])
    return known


def _get_known_fields_for_storage(provider):
    """Return set of known source field names for a storage provider."""
    mapping = _STORAGE_FIELD_MAP.get(provider, {})
    known = set()
    for source_key in mapping.values():
        known.add(source_key.split(".")[0])
    return known


def _collect_additional_fields(raw_item, known_fields):
    """Collect fields from raw_item that are not in known_fields."""
    additional = {}
    if not isinstance(raw_item, dict):
        return additional
    for key, value in raw_item.items():
        if key not in known_fields:
            additional[key] = value
    return additional


def _normalize_state(state_value, provider):
    """Normalize instance state to a standard string."""
    if state_value is None:
        return None
    if isinstance(state_value, dict):
        # AWS returns State as {"Name": "running", "Code": 16}
        return state_value.get("Name", str(state_value))
    return str(state_value).lower()


def _normalize_attached(value, provider):
    """Normalize 'attached' field to a boolean."""
    if value is None:
        return None
    if provider == "aws":
        # AWS Attachments is a list; non-empty means attached
        if isinstance(value, list):
            return len(value) > 0
        return bool(value)
    elif provider == "azure":
        # Azure managedBy is a string (resource ID) or None
        return value is not None and value != ""
    elif provider == "gcp":
        # GCP users is a list of attached instance URLs
        if isinstance(value, list):
            return len(value) > 0
        return bool(value)
    return bool(value)


def _normalize_multi_az(value, provider):
    """Normalize multiAZ field to a boolean."""
    if value is None:
        return None
    if provider == "aws":
        return bool(value)
    elif provider == "azure":
        # Azure uses strings like "ZoneRedundant" or "SameZone"
        if isinstance(value, str):
            return value.lower() in ("zoneredundant", "enabled", "true")
        return bool(value)
    elif provider == "gcp":
        # GCP uses "REGIONAL" for multi-AZ
        if isinstance(value, str):
            return value.upper() == "REGIONAL"
        return bool(value)
    return bool(value)


def _normalize_storage_size(value, provider):
    """Normalize storage size to integer GB."""
    if value is None:
        return None
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    # Azure sometimes returns MB
    if provider == "azure":
        # If field name was storageMB, convert to GB
        if size > 10000:  # Likely in MB
            return size // 1024
    return size


def normalize_compute_response(raw, provider):
    """
    Transform provider-specific compute data to normalized schema.

    Args:
        raw: Raw provider response dict. Expected to contain an 'instances' list
             or provider-specific keys with instance data.
        provider: String identifier ('aws', 'azure', 'gcp').

    Returns:
        Normalized dict with 'instances' list and 'count'.
    """
    if not isinstance(raw, dict):
        return {"instances": [], "count": 0}

    # Extract instance list from raw response
    raw_instances = _extract_instance_list(raw, provider, "compute")

    normalized_instances = []
    mapping = _COMPUTE_FIELD_MAP.get(provider, {})
    known_fields = _get_known_fields_for_compute(provider)

    for item in raw_instances:
        if not isinstance(item, dict):
            continue

        # Extract name (special case for AWS tags)
        if provider == "aws":
            name = _extract_aws_instance_name(item)
        else:
            name_key = mapping.get("name")
            name = _safe_get(item, name_key) if name_key else None

        # Extract state with normalization
        state_key = mapping.get("state")
        state_raw = _safe_get(item, state_key) if state_key else None
        state = _normalize_state(state_raw, provider)

        # Extract launch time
        launch_key = mapping.get("launchTime")
        launch_time = _safe_get(item, launch_key) if launch_key else None
        if launch_time is not None:
            launch_time = str(launch_time)

        # Collect additional fields for providerMetadata
        additional = _collect_additional_fields(item, known_fields)

        instance = {
            "instanceId": _safe_get(item, mapping.get("instanceId", "")) if mapping.get("instanceId") else None,
            "instanceType": _safe_get(item, mapping.get("instanceType", "")) if mapping.get("instanceType") else None,
            "state": state,
            "name": name,
            "region": _safe_get(item, mapping.get("region", "")) if mapping.get("region") else None,
            "launchTime": launch_time,
            "providerMetadata": {
                "provider": provider,
                "nativeId": _safe_get(item, mapping.get("nativeId", "")) if mapping.get("nativeId") else None,
                "additionalFields": additional,
            },
        }
        normalized_instances.append(instance)

    return {
        "instances": normalized_instances,
        "count": len(normalized_instances),
    }


def normalize_cost_response(raw, provider):
    """
    Transform provider-specific cost data to normalized schema.

    Args:
        raw: Raw provider response dict with cost data.
        provider: String identifier ('aws', 'azure', 'gcp', 'openai').

    Returns:
        Normalized dict with totalCost, currency, period, serviceBreakdown,
        dailyCosts, and providerMetadata.
    """
    if not isinstance(raw, dict):
        return {
            "totalCost": None,
            "currency": None,
            "period": None,
            "serviceBreakdown": None,
            "dailyCosts": None,
            "providerMetadata": {"provider": provider, "source": None},
        }

    # Extract total cost
    total_cost = (
        raw.get("totalCost")
        or raw.get("total_cost")
        or raw.get("TotalCost")
        or raw.get("amount")
    )
    if total_cost is not None:
        try:
            total_cost = float(total_cost)
        except (TypeError, ValueError):
            total_cost = None

    # Extract currency
    currency = (
        raw.get("currency")
        or raw.get("Currency")
        or raw.get("billingCurrency")
        or "USD"
    )

    # Extract period
    period = (
        raw.get("period")
        or raw.get("Period")
        or raw.get("timePeriod")
        or raw.get("TimePeriod")
    )
    if isinstance(period, dict):
        # AWS returns TimePeriod as {"Start": ..., "End": ...}
        start = period.get("Start", period.get("start", ""))
        end = period.get("End", period.get("end", ""))
        period = f"{start} to {end}" if start or end else None
    elif period is not None:
        period = str(period)

    # Extract service breakdown
    service_breakdown = _extract_service_breakdown(raw, provider)

    # Extract daily costs
    daily_costs = _extract_daily_costs(raw, provider)

    # Extract source (cache vs live)
    source = raw.get("source", raw.get("_source", None))

    # Determine known fields for providerMetadata
    known_cost_fields = {
        "totalCost", "total_cost", "TotalCost", "amount",
        "currency", "Currency", "billingCurrency",
        "period", "Period", "timePeriod", "TimePeriod",
        "serviceBreakdown", "service_breakdown", "ServiceBreakdown",
        "services", "Groups", "ResultsByTime",
        "dailyCosts", "daily_costs", "DailyCosts",
        "source", "_source",
    }
    additional = {k: v for k, v in raw.items() if k not in known_cost_fields}

    provider_metadata = {
        "provider": provider,
        "source": source,
    }
    if additional:
        provider_metadata["additionalFields"] = additional

    return {
        "totalCost": total_cost,
        "currency": currency,
        "period": period,
        "serviceBreakdown": service_breakdown,
        "dailyCosts": daily_costs,
        "providerMetadata": provider_metadata,
    }


def normalize_database_response(raw, provider):
    """
    Transform provider-specific database data to normalized schema.

    Args:
        raw: Raw provider response dict with database instance data.
        provider: String identifier ('aws', 'azure', 'gcp').

    Returns:
        Normalized dict with 'instances' list and 'count'.
    """
    if not isinstance(raw, dict):
        return {"instances": [], "count": 0}

    raw_instances = _extract_instance_list(raw, provider, "database")

    normalized_instances = []
    mapping = _DATABASE_FIELD_MAP.get(provider, {})
    known_fields = _get_known_fields_for_database(provider)

    for item in raw_instances:
        if not isinstance(item, dict):
            continue

        # Extract and normalize multiAZ
        multi_az_key = mapping.get("multiAZ")
        multi_az_raw = _safe_get(item, multi_az_key) if multi_az_key else None
        multi_az = _normalize_multi_az(multi_az_raw, provider)

        # Extract and normalize storage size
        storage_key = mapping.get("storageSizeGB")
        storage_raw = _safe_get(item, storage_key) if storage_key else None
        storage_size = _normalize_storage_size(storage_raw, provider)

        # Collect additional fields
        additional = _collect_additional_fields(item, known_fields)

        instance = {
            "instanceId": _safe_get(item, mapping.get("instanceId", "")) if mapping.get("instanceId") else None,
            "instanceType": _safe_get(item, mapping.get("instanceType", "")) if mapping.get("instanceType") else None,
            "engine": _safe_get(item, mapping.get("engine", "")) if mapping.get("engine") else None,
            "status": _safe_get(item, mapping.get("status", "")) if mapping.get("status") else None,
            "storageSizeGB": storage_size,
            "multiAZ": multi_az,
            "providerMetadata": {
                "provider": provider,
                "nativeId": _safe_get(item, mapping.get("nativeId", "")) if mapping.get("nativeId") else None,
            },
        }

        if additional:
            instance["providerMetadata"]["additionalFields"] = additional

        normalized_instances.append(instance)

    return {
        "instances": normalized_instances,
        "count": len(normalized_instances),
    }


def normalize_storage_response(raw, provider):
    """
    Transform provider-specific storage volume data to normalized schema.

    Args:
        raw: Raw provider response dict with storage volume data.
        provider: String identifier ('aws', 'azure', 'gcp').

    Returns:
        Normalized dict with 'volumes' list and 'count'.
    """
    if not isinstance(raw, dict):
        return {"volumes": [], "count": 0}

    raw_volumes = _extract_volume_list(raw, provider)

    normalized_volumes = []
    mapping = _STORAGE_FIELD_MAP.get(provider, {})
    known_fields = _get_known_fields_for_storage(provider)

    for item in raw_volumes:
        if not isinstance(item, dict):
            continue

        # Extract and normalize sizeGB
        size_key = mapping.get("sizeGB")
        size_raw = _safe_get(item, size_key) if size_key else None
        size_gb = None
        if size_raw is not None:
            try:
                size_gb = int(size_raw)
            except (TypeError, ValueError):
                size_gb = None

        # Extract and normalize attached
        attached_key = mapping.get("attached")
        attached_raw = _safe_get(item, attached_key) if attached_key else None
        attached = _normalize_attached(attached_raw, provider)

        # Collect additional fields
        additional = _collect_additional_fields(item, known_fields)

        volume = {
            "volumeId": _safe_get(item, mapping.get("volumeId", "")) if mapping.get("volumeId") else None,
            "volumeType": _safe_get(item, mapping.get("volumeType", "")) if mapping.get("volumeType") else None,
            "sizeGB": size_gb,
            "state": _safe_get(item, mapping.get("state", "")) if mapping.get("state") else None,
            "attached": attached,
            "providerMetadata": {
                "provider": provider,
                "nativeId": _safe_get(item, mapping.get("nativeId", "")) if mapping.get("nativeId") else None,
            },
        }

        if additional:
            volume["providerMetadata"]["additionalFields"] = additional

        normalized_volumes.append(volume)

    return {
        "volumes": normalized_volumes,
        "count": len(normalized_volumes),
    }


def normalize_object_storage_response(raw, provider):
    """
    Transform provider-specific object storage data to normalized schema.

    Args:
        raw: Raw provider response dict with bucket/container data.
        provider: String identifier ('aws', 'azure', 'gcp').

    Returns:
        Normalized dict with 'buckets' list, 'count', and 'providerMetadata'.
    """
    if not isinstance(raw, dict):
        return {"buckets": [], "count": 0, "providerMetadata": {"provider": provider}}

    raw_buckets = _extract_bucket_list(raw, provider)

    normalized_buckets = []
    known_fields = set()

    for item in raw_buckets:
        if not isinstance(item, dict):
            continue

        bucket = _normalize_single_bucket(item, provider)
        normalized_buckets.append(bucket)

    # Collect top-level additional fields from raw
    known_top_fields = {
        "Buckets", "buckets", "items", "containers",
        "Owner", "owner", "kind", "nextPageToken",
    }
    additional = {k: v for k, v in raw.items() if k not in known_top_fields}

    provider_metadata = {"provider": provider}
    if additional:
        provider_metadata["additionalFields"] = additional

    return {
        "buckets": normalized_buckets,
        "count": len(normalized_buckets),
        "providerMetadata": provider_metadata,
    }


# --- Private helper functions ---


def _extract_instance_list(raw, provider, resource_type):
    """Extract the list of instances from various response shapes."""
    # Try common keys
    for key in ("instances", "Instances", "Reservations", "items",
                "DBInstances", "value", "databases"):
        if key in raw:
            val = raw[key]
            if isinstance(val, list):
                # AWS EC2 wraps instances in Reservations
                if key == "Reservations":
                    instances = []
                    for reservation in val:
                        if isinstance(reservation, dict):
                            instances.extend(reservation.get("Instances", []))
                    return instances
                return val
    # Fallback: if raw itself looks like a single instance, wrap it
    if resource_type == "compute" and "instanceId" in raw:
        return [raw]
    if resource_type == "database" and ("DBInstanceIdentifier" in raw or "instanceId" in raw):
        return [raw]
    return []


def _extract_volume_list(raw, provider):
    """Extract the list of volumes from various response shapes."""
    for key in ("volumes", "Volumes", "items", "value", "disks"):
        if key in raw:
            val = raw[key]
            if isinstance(val, list):
                return val
    return []


def _extract_bucket_list(raw, provider):
    """Extract the list of buckets/containers from various response shapes."""
    for key in ("Buckets", "buckets", "items", "containers", "value"):
        if key in raw:
            val = raw[key]
            if isinstance(val, list):
                return val
    return []


def _extract_service_breakdown(raw, provider):
    """Extract service-level cost breakdown from raw cost data."""
    # Direct field
    breakdown = (
        raw.get("serviceBreakdown")
        or raw.get("service_breakdown")
        or raw.get("ServiceBreakdown")
        or raw.get("services")
    )

    if isinstance(breakdown, list):
        normalized = []
        for item in breakdown:
            if isinstance(item, dict):
                service_name = (
                    item.get("serviceName")
                    or item.get("service_name")
                    or item.get("ServiceName")
                    or item.get("service")
                    or item.get("name")
                )
                cost = item.get("cost") or item.get("Cost") or item.get("amount")
                try:
                    cost = float(cost) if cost is not None else None
                except (TypeError, ValueError):
                    cost = None
                normalized.append({"serviceName": service_name, "cost": cost})
        return normalized if normalized else None

    # AWS Cost Explorer ResultsByTime with Groups
    results_by_time = raw.get("ResultsByTime")
    if isinstance(results_by_time, list):
        service_totals = {}
        for period_result in results_by_time:
            if not isinstance(period_result, dict):
                continue
            groups = period_result.get("Groups", [])
            for group in groups:
                if not isinstance(group, dict):
                    continue
                keys = group.get("Keys", [])
                metrics = group.get("Metrics", {})
                svc_name = keys[0] if keys else "Unknown"
                amount = 0.0
                if isinstance(metrics, dict):
                    for metric_val in metrics.values():
                        if isinstance(metric_val, dict):
                            try:
                                amount += float(metric_val.get("Amount", 0))
                            except (TypeError, ValueError):
                                pass
                service_totals[svc_name] = service_totals.get(svc_name, 0.0) + amount
        if service_totals:
            return [{"serviceName": k, "cost": v} for k, v in service_totals.items()]

    return None


def _extract_daily_costs(raw, provider):
    """Extract daily cost breakdown from raw cost data."""
    daily = (
        raw.get("dailyCosts")
        or raw.get("daily_costs")
        or raw.get("DailyCosts")
    )

    if isinstance(daily, list):
        normalized = []
        for item in daily:
            if isinstance(item, dict):
                date = item.get("date") or item.get("Date") or item.get("day")
                cost = item.get("cost") or item.get("Cost") or item.get("amount")
                try:
                    cost = float(cost) if cost is not None else None
                except (TypeError, ValueError):
                    cost = None
                normalized.append({"date": str(date) if date else None, "cost": cost})
        return normalized if normalized else None

    # AWS ResultsByTime can also provide daily data
    results_by_time = raw.get("ResultsByTime")
    if isinstance(results_by_time, list) and len(results_by_time) > 1:
        daily_list = []
        for period_result in results_by_time:
            if not isinstance(period_result, dict):
                continue
            time_period = period_result.get("TimePeriod", {})
            date = time_period.get("Start") if isinstance(time_period, dict) else None
            total = period_result.get("Total", {})
            amount = 0.0
            if isinstance(total, dict):
                for metric_val in total.values():
                    if isinstance(metric_val, dict):
                        try:
                            amount += float(metric_val.get("Amount", 0))
                        except (TypeError, ValueError):
                            pass
            if date:
                daily_list.append({"date": date, "cost": amount})
        return daily_list if daily_list else None

    return None


def _normalize_single_bucket(item, provider):
    """Normalize a single bucket/container entry."""
    if provider == "aws":
        return {
            "name": item.get("Name"),
            "creationDate": str(item.get("CreationDate")) if item.get("CreationDate") else None,
            "providerMetadata": {
                "provider": provider,
                "nativeId": item.get("Name"),
                "additionalFields": {
                    k: v for k, v in item.items()
                    if k not in ("Name", "CreationDate")
                },
            },
        }
    elif provider == "azure":
        return {
            "name": item.get("name"),
            "creationDate": _safe_get(item, "properties.creationTime"),
            "providerMetadata": {
                "provider": provider,
                "nativeId": item.get("id"),
                "additionalFields": {
                    k: v for k, v in item.items()
                    if k not in ("name", "id", "properties")
                },
            },
        }
    elif provider == "gcp":
        return {
            "name": item.get("name"),
            "creationDate": item.get("timeCreated"),
            "providerMetadata": {
                "provider": provider,
                "nativeId": item.get("selfLink") or item.get("id"),
                "additionalFields": {
                    k: v for k, v in item.items()
                    if k not in ("name", "timeCreated", "selfLink", "id")
                },
            },
        }
    else:
        # Generic fallback
        return {
            "name": item.get("name") or item.get("Name"),
            "creationDate": None,
            "providerMetadata": {
                "provider": provider,
                "nativeId": item.get("id") or item.get("name"),
                "additionalFields": {
                    k: v for k, v in item.items()
                    if k not in ("name", "Name", "id")
                },
            },
        }
