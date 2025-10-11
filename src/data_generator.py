import math
import uuid
import time
import random
from src.utils import haversine_distance, log_output, TRACK_POINT_DECIMAL_PLACES, get_current_epoch_ms, SportsUploaderError

def interpolate_points(start_lat, start_lon, end_lat, end_lon, speed_mps, interval_seconds):
    """
    在起点和终点之间以给定速度和采样间隔插值生成轨迹点。
    返回一个包含轨迹点字典的列表，以及这段的距离和时长。
    注意：这里生成的点不包含locatetime，由generate_running_data统一分配。
    """
    points = []

    start_lat_calc = float(f"{start_lat:.14f}")
    start_lon_calc = float(f"{start_lon:.14f}")
    end_lat_calc = float(f"{end_lat:.14f}")
    end_lon_calc = float(f"{end_lon:.14f}")

    start_lat_rad = math.radians(start_lat_calc)
    start_lon_rad = math.radians(start_lon_calc)
    end_lat_rad = math.radians(end_lat_calc)
    end_lon_rad = math.radians(end_lon_calc)

    segment_distance = haversine_distance(start_lat_calc, start_lon_calc, end_lat_calc, end_lon_calc)
    segment_duration_seconds = segment_distance / speed_mps

    num_steps = math.ceil(segment_duration_seconds / interval_seconds)
    if num_steps <= 1 and segment_distance > 0:
        num_steps = 1
    elif segment_distance == 0:
        num_steps = 0

    if num_steps == 0:
        formatted_lat = f"{start_lat_calc:.{TRACK_POINT_DECIMAL_PLACES}f}"
        formatted_lon = f"{start_lon_calc:.{TRACK_POINT_DECIMAL_PLACES}f}"
        points.append({
            "latLng": {"latitude": float(formatted_lat), "longitude": float(formatted_lon)},
            "location": f"{formatted_lon},{formatted_lat}",
            "step": 0
        })
        return points, segment_distance, math.ceil(segment_duration_seconds)

    for i in range(num_steps + 1):
        fraction = i / num_steps

        interp_lat_rad = start_lat_rad + fraction * (end_lat_rad - start_lat_rad)
        interp_lon_rad = start_lon_rad + fraction * (end_lon_rad - start_lon_rad)

        interp_lat = math.degrees(interp_lat_rad)
        interp_lon = math.degrees(interp_lon_rad)

        formatted_lat = f"{interp_lat:.{TRACK_POINT_DECIMAL_PLACES}f}"
        formatted_lon = f"{interp_lon:.{TRACK_POINT_DECIMAL_PLACES}f}"

        points.append({
            "latLng": {"latitude": float(formatted_lat), "longitude": float(formatted_lon)},
            "location": f"{formatted_lon},{formatted_lat}",
            "step": 0
        })

    final_end_lat_formatted = float(f"{end_lat_calc:.{TRACK_POINT_DECIMAL_PLACES}f}")
    final_end_lon_formatted = float(f"{end_lon_calc:.{TRACK_POINT_DECIMAL_PLACES}f}")

    if abs(points[-1]['latLng']['latitude'] - final_end_lat_formatted) > 1e-10 or \
            abs(points[-1]['latLng']['longitude'] - final_end_lon_formatted) > 1e-10:
        points[-1] = {
            "latLng": {"latitude": final_end_lat_formatted, "longitude": final_end_lon_formatted},
            "location": f"{final_end_lon_formatted},{final_end_lat_formatted}",
            "step": 0
        }

    return points, segment_distance, math.ceil(segment_duration_seconds)


def split_track_into_segments(all_points_with_time, total_duration_sec, min_segment_points=5, stop_check_cb=None):
    """
    将所有带有locatetime的轨迹点拆分为多个轨迹段。
    并分配不同的 status 和 tstate。
    """
    tracks = []

    status_map = {
        "normal": "0",
        "stop": "0",
        "invalid": "2",
    }

    current_start_point_idx = 0

    if not all_points_with_time:
        return tracks

    while current_start_point_idx < len(all_points_with_time):
        if stop_check_cb and stop_check_cb():
            log_output("轨迹生成被中断。", "warning")
            raise SportsUploaderError("任务已停止。")

        segment_points = []

        remaining_points = len(all_points_with_time) - current_start_point_idx
        if remaining_points <= min_segment_points:
            segment_length = remaining_points
        else:
            segment_length = random.randint(min_segment_points, max(min_segment_points, remaining_points // 3))
            if segment_length == 1 and remaining_points > 1:
                segment_length = min_segment_points

        segment_points = all_points_with_time[current_start_point_idx: current_start_point_idx + segment_length]
        current_start_point_idx += segment_length

        if not segment_points:
            continue

        rand_val = random.random()
        if rand_val < 0.8:
            segment_status = "normal"
        elif rand_val < 0.9:
            segment_status = "invalid"
        else:
            segment_status = "stop"

        segment_tstate = status_map.get(segment_status, "0")

        segment_distance = 0
        if len(segment_points) > 1:
            for i in range(len(segment_points) - 1):
                p1 = segment_points[i]['latLng']
                p2 = segment_points[i + 1]['latLng']
                segment_distance += haversine_distance(p1['latitude'], p1['longitude'], p2['latitude'], p2['longitude'])

        segment_start_time_ms = segment_points[0]['locatetime']
        segment_end_time_ms = segment_points[-1]['locatetime']
        segment_duration_sec = math.ceil((segment_end_time_ms - segment_start_time_ms) / 1000)

        tracks.append({
            "counts": len(segment_points),
            "distance": segment_distance,
            "duration": segment_duration_sec,
            "points": segment_points,
            "status": segment_status,
            "trid": str(uuid.uuid4()),
            "tstate": segment_tstate,
            "stime": segment_start_time_ms // 1000,
            "etime": segment_end_time_ms // 1000
        })

    return tracks


def generate_running_data_payload(config, required_signpoints, point_rules_data, log_cb=None, stop_check_cb=None):
    """
    生成符合POST请求体格式的跑步数据，并整合打卡点。
    """
    # 快速生成路径：忽略用户自定义多段插值，直接生成一段大约 5km、配速约 3.5min/km 的轨迹。
    target_distance_m = 5000  # 约 5km
    pace_sec_per_km = 3.5 * 60  # 3.5 分钟每公里 -> 秒/公里
    total_duration_sec = int(round(pace_sec_per_km * (target_distance_m / 1000.0)))

    interval_seconds = int(config.get('INTERVAL_SECONDS', 3))
    if interval_seconds <= 0:
        interval_seconds = 3

    # 计算每个采样点的数量（包含起点和终点）
    num_intervals = max(1, math.ceil(total_duration_sec / interval_seconds))
    # 为保证覆盖终点，点数为 num_intervals + 1
    num_points = num_intervals + 1

    # 计算每秒速度（m/s）
    speed_mps = target_distance_m / total_duration_sec if total_duration_sec > 0 else config.get('RUNNING_SPEED_MPS', 2.5)

    # 起点经纬度
    start_lat = float(config.get('START_LATITUDE', 31.031599))
    start_lon = float(config.get('START_LONGITUDE', 121.442938))

    # 简单的经度偏移计算：在相同纬度上向东移动累计距离以达到目标距离。
    # 1度纬度约等于 111111 米，1度经度约等于 111111 * cos(lat) 米
    lat_rad = math.radians(start_lat)
    meters_per_degree_lon = 111111 * math.cos(lat_rad)

    full_interpolated_points_with_time = []

    current_locatetime_ms = config['START_TIME_EPOCH_MS'] if config.get('START_TIME_EPOCH_MS') is not None else get_current_epoch_ms()

    for i in range(num_points):
        if stop_check_cb and stop_check_cb():
            log_output("轨迹生成被中断。", "warning")
            raise SportsUploaderError("任务已停止。")

        elapsed_sec = min(i * interval_seconds, total_duration_sec)
        traveled_m = min(elapsed_sec * speed_mps, target_distance_m)

        delta_lon_deg = traveled_m / meters_per_degree_lon if meters_per_degree_lon != 0 else 0
        point_lat = start_lat
        point_lon = start_lon + delta_lon_deg

        formatted_lat = f"{point_lat:.{TRACK_POINT_DECIMAL_PLACES}f}"
        formatted_lon = f"{point_lon:.{TRACK_POINT_DECIMAL_PLACES}f}"

        point = {
            "latLng": {"latitude": float(formatted_lat), "longitude": float(formatted_lon)},
            "location": f"{formatted_lon},{formatted_lat}",
            "step": 0,
            "locatetime": current_locatetime_ms
        }

        full_interpolated_points_with_time.append(point)
        current_locatetime_ms += interval_seconds * 1000

    total_overall_distance = target_distance_m

    actual_total_duration_sec = 0
    if full_interpolated_points_with_time:
        first_point_time_ms = full_interpolated_points_with_time[0]['locatetime']
        last_point_time_ms = full_interpolated_points_with_time[-1]['locatetime']
        actual_total_duration_sec = math.ceil((last_point_time_ms - first_point_time_ms + config['INTERVAL_SECONDS'] * 1000) / 1000)

    tracks_list = split_track_into_segments(full_interpolated_points_with_time, actual_total_duration_sec, stop_check_cb=stop_check_cb)
    actual_total_distance = sum(t['distance'] for t in tracks_list)

    run_id = point_rules_data.get('rules', {}).get('id', 6)
    if run_id == 6:
        run_id = 9

    sp_avg = 0
    if actual_total_distance > 0 and actual_total_duration_sec > 0:
        sp_avg = actual_total_duration_sec / (actual_total_distance / 1000) / 60
        sp_avg = round(sp_avg)

    rules_meta = point_rules_data.get('rules', {})
    min_sp_s_per_km = rules_meta.get('spmin', 180)
    max_sp_s_per_km = rules_meta.get('spmax', 540)

    sp_avg_s_per_km = sp_avg * 60 if sp_avg > 0 else 0

    if actual_total_distance > 0:
        if sp_avg_s_per_km < min_sp_s_per_km:
            log_output(f"Warning: Calculated pace {sp_avg} min/km ({sp_avg_s_per_km:.0f} s/km) is faster than {min_sp_s_per_km / 60:.0f} min/km ({min_sp_s_per_km:.0f} s/km). Adjusting to minimum allowed pace.", "warning", log_cb)
            sp_avg = math.ceil(min_sp_s_per_km / 60)
        elif sp_avg_s_per_km > max_sp_s_per_km:
            log_output(f"Warning: Calculated pace {sp_avg} min/km ({sp_avg_s_per_km:.0f} s/km) is slower than {max_sp_s_per_km / 60:.0f} min/km ({max_sp_s_per_km:.0f} s/km). Adjusting to maximum allowed pace.", "warning", log_cb)
            sp_avg = math.floor(max_sp_s_per_km / 60)

    request_body = [
        {
            "fravg": 0,
            "id": run_id,
            "sid": str(uuid.uuid4()),
            "signpoints": [],
            "spavg": sp_avg,
            "state": "0",
            "tracks": tracks_list,
            "userId": config['USER_ID']
        }
    ]
    return request_body, actual_total_distance, actual_total_duration_sec