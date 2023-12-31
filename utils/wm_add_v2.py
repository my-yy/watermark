import pdb

import torch
import numpy as np
from utils import bin_util
from utils import metric_util
import tqdm
import time

fix_pattern = [1, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0,
               0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1,
               1, 1, 0, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1,
               1, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 0,
               0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1, 0]


# def create_parcel_message(len_start_bit, num_bit, wm_text, verbose=False):
#     # 2.起始bit
#     # start_bit = np.array([0] * len_start_bit)
#     start_bit = fix_pattern[0:len_start_bit]
#     error_prob = 2 ** len_start_bit / 10000
#     # todo:考虑threshold的时候的错误率呢?
#     if verbose:
#         print("起始bit长度:%d,错误率:%.1f万" % (len(start_bit), error_prob))
#
#     # 3.信息内容
#     length_msg = num_bit - len(start_bit)
#     if wm_text:
#         msg_arr = bin_util.hexStr2BinArray(wm_text)
#     else:
#         msg_arr = np.random.choice([0, 1], size=length_msg)
#
#     # 4.封装信息
#     watermark = np.concatenate([start_bit, msg_arr])
#     assert len(watermark) == num_bit
#     return start_bit, msg_arr, watermark


def add_watermark(bit_arr, data, num_point, shift_range, device, model, min_snr, max_snr):
    t1 = time.time()
    # 1.获得区块大小
    chunk_size = num_point + int(num_point * shift_range)

    output_chunks = []
    encoded_sections = 0
    skip_sections = 0
    idx_trunck = -1
    # for i in range(0, len(data), chunk_size):
    for i in tqdm.tqdm(range(0, len(data), chunk_size), desc="Processing"):
        idx_trunck += 1
        current_chunk = data[i:i + chunk_size].copy()
        # 最后一块，长度不足
        if len(current_chunk) < chunk_size:
            output_chunks.append(current_chunk)
            break

        # 处理区块: [水印区|间隔区]
        current_chunk_cover_area = current_chunk[0:num_point]
        current_chunk_shift_area = current_chunk[num_point:]
        current_chunk_cover_area_wmd, state = encode_trunck_with_snr_check(idx_trunck, current_chunk_cover_area,
                                                                           bit_arr,
                                                                           device, model, min_snr, max_snr)

        if state == "skip":
            skip_sections += 1
        else:
            encoded_sections += 1

        output = np.concatenate([current_chunk_cover_area_wmd, current_chunk_shift_area])
        assert output.shape == current_chunk.shape
        output_chunks.append(output)

    assert len(output_chunks) > 0
    reconstructed_array = np.concatenate(output_chunks)
    time_cost = time.time() - t1

    info = {
        "time_cost": time_cost,
        "encoded_sections": encoded_sections,
        "skip_sections": skip_sections,
    }
    return reconstructed_array, info


def encode_trunck_with_snr_check(idx_trunck, signal, wm, device, model, min_snr, max_snr):
    signal_for_encode = signal
    encode_times = 0
    while True:
        encode_times += 1
        signal_wmd = encode_trunck(signal_for_encode, wm, device, model)
        snr = metric_util.signal_noise_ratio(signal, signal_wmd)
        if encode_times == 1 and snr < min_snr:
            print("skip section:%d, snr too low:%.1f" % (idx_trunck, min_snr))
            return signal, "skip"

        if snr < max_snr:
            return signal_wmd, encode_times
        # snr is too hugh
        signal_for_encode = signal_wmd

        if encode_times > 10:
            return signal_wmd, encode_times


def encode_trunck(trunck, wm, device, model):
    with torch.no_grad():
        signal = torch.FloatTensor(trunck).to(device)[None]
        message = torch.FloatTensor(np.array(wm)).to(device)[None]
        signal_wmd_tensor = model.encode(signal, message)
        signal_wmd = signal_wmd_tensor.detach().cpu().numpy().squeeze()
        return signal_wmd
