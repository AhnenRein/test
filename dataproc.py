from django.shortcuts import get_object_or_404, render, get_list_or_404
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse

from threading import Timer

from .models import ExcelFile, InputParams
from batteryserver.settings import MEDIA_ROOT
from datetime import time, datetime
import xlrd
import os

import numpy as np

import RPi.GPIO as GPIO


btnList = [
    {
        'id': 'btnA',
        'name': 'ButtonA',
        'status': False,
        'color': 'blue',
    },
    {
        'id': 'btnB',
        'name': 'ButtonB',
        'status': False,
        'color': 'blue',
    },
    {
        'id': 'btnC',
        'name': 'ButtonC',
        'status': False,
        'color': 'blue',
    },
    {
        'id': 'btnD',
        'name': 'ButtonD',
        'status': False,
        'color': 'blue',
    },
    {
        'id': 'btnE',
        'name': 'ButtonE',
        'status': False,
        'color': 'blue',
    },
]

# 定义全局变量
currentParamSetModel = 'modelA'
last_bat = dict()
except_bat = dict()
last_alt_dict = dict() # 新负载
kap_alt_dict = dict()  # 当前电池电量
l_last_dict = dict()   # 充电功率
polor_dict = dict()
e_last_dict = dict()
power_dict = dict()

isGPIOInit = True
ch1 = 17
ch2 = 18
ch3 = 22
ch4 = 27
ch5 = 23

GPIO.cleanup()
GPIO.setmode(GPIO.BCM)
GPIO.setup(ch1, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(ch2, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(ch3, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(ch4, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(ch5, GPIO.OUT, initial=GPIO.HIGH)


pwmCh1 = GPIO.PWM(ch1, 100)
pwmCh2 = GPIO.PWM(ch2, 100)
pwmCh3 = GPIO.PWM(ch3, 100)
pwmCh4 = GPIO.PWM(ch4, 100)
pwmCh5 = GPIO.PWM(ch5, 100)

pwmCh1.start(100)
pwmCh2.start(100)
pwmCh3.start(100)
pwmCh4.start(100)
pwmCh5.start(100)

def initGPIO():

    global pwmCh1
    global pwmCh2
    global pwmCh3
    global pwmCh4
    global pwmCh5

    global ch1
    global ch2
    global ch3
    global ch4
    global ch5

    global isGPIOInit

    print('init gpio')
    if isGPIOInit:
        return


def runCh1(duty):
    global pwmCh1
    pwmCh1.ChangeDutyCycle(duty)

def runCh2(duty):
    global pwmCh2
    pwmCh2.ChangeDutyCycle(duty)

def runCh3(duty):
    global pwmCh3
    pwmCh3.ChangeDutyCycle(duty)

def runCh4(duty):
    global pwmCh4
    pwmCh4.ChangeDutyCycle(duty)

def runCh5(duty):
    global pwmCh5
    pwmCh5.ChangeDutyCycle(duty)


def createList():
    time_array = list()
    last_alt = list()
    last_neu = list()
    kap_neu = list()
    soc = list()

    return time_array, last_alt, last_neu, kap_neu, soc

def modelA(table, cur_model):

# 初始化数据
    global last_bat
    global except_bat
    last_bat.clear()
    except_bat.clear()
    last_alt_dict.clear()
    kap_alt_dict.clear()
    l_last_dict.clear()

    global power_dict

    # 结果列表
    last_alt = list() # 新负载
    last_neu = list() # 新电量
    soc = list()      # 电池电量

    # 中间变量
    kap_neu = list()

    # 时间列
    time_array = list() # []列表 {}字典
    time_array.extend(transToTime(table.col_values(0)[1:]))    

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)# 查找当前模式参数

    if len(obj) == 0:
        return time_array, last_alt, last_neu, kap_neu, soc

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'line')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')

    # 电价列
    col03 = table.col_values(3)

    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    power_dict.clear()
    for t, p in zip(time_array, col01[2:]):
        power_dict[t] = p
    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()

    for alt, c_t in zip(last_alt, time_array):
        c_time = datetime.strptime(c_t,'%H:%M:%S').time()

        # last_bat[c_t] = 
        # except_bat[c_t] = 

        if alt > 0: # last_alt大于0的情况

            if kap_alt == 0: # 当前电池电量为零的情况

                kap_neu.append(0)
                soc.append(0)
                last_neu.append(alt)

                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / e_last

            else:
                # 求最小值
                ew = min(e_last, alt)
                ew = min(ew, kap_alt * 4)

                # 保存计算结果
                last_neu.append(alt - ew)
                kap_neu.append(kap_alt - ew / 4)
                soc.append(((kap_alt - (ew / 4)) / max_kap) * 100)
                kap_alt = ((kap_alt - ew / 4))


                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / e_last

        else:# last_alt 小于0的情况

            if kap_alt == max_kap: # kap_alt 到达最大值的情况
                # 保存计算结果
                last_neu.append(alt)
                kap_neu.append(max_kap)
                soc.append(100.0)
                
                # 更新当前电量
                kap_alt = max_kap

                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / e_last

            else:
                # 计算最小值
                dif_kap = max_kap - kap_alt
                ew = min(abs(alt), dif_kap * 4.0)
                ew = min(ew, l_last)

                # 保存计算结果
                last_neu.append(alt + ew)
                kap_neu.append(kap_alt + (ew / 4))
                soc.append(((kap_alt + (ew / 4)) / max_kap) * 100)
            
                # 更新当前电量
                kap_alt = ((kap_alt + (ew / 4)))


                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / e_last

        last_alt_dict[c_t] = alt
        l_last_dict[c_t] = l_last
        kap_alt_dict[c_t] = kap_alt
        e_last_dict[c_t] = e_last

        last_bat[c_t] = last_neu[-1]
        except_bat[c_t] = kap_alt / e_last

    return time_array, last_alt, last_neu, kap_neu, soc

def modelB(table, cur_model):

    global last_bat
    global except_bat
    last_bat.clear()
    except_bat.clear()
    last_alt_dict.clear()
    kap_alt_dict.clear()
    l_last_dict.clear()


    # 结果列表
    last_alt = list()
    last_neu = list()
    soc = list()

    # 中间变量
    kap_neu = list()

    # 时间列
    time_array = []
    time_array.extend(transToTime(table.col_values(0)[1:]))    

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    if len(obj) == 0:
        return time_array, last_alt, last_neu, kap_neu, soc

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率
    a_laden = obj[0].a_laden
    e_laden = obj[0].e_laden
    a_entladen = obj[0].a_entladen
    e_entladen = obj[0].e_entladen

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')

    # 电价列
    col03 = table.col_values(3)

    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()

    r_soc = 0
    for alt, c_t in zip(last_alt, time_array[1:]):

        c_time = datetime.strptime(c_t,'%H:%M:%S').time()

        if alt > 0: # last_alt大于0的情况

            if c_time >= a_entladen and e_entladen >= c_time:
                ew = min(alt, kap_alt * 4)
                ew = min(ew, e_last)

                last_neu.append(alt - ew)
                kap_neu.append(kap_alt - (ew / 4))
                soc.append((kap_neu/max_kap) * 100)
                r_soc = (kap_neu/max_kap) * 100

                kap_alt = kap_alt - (ew / 4)

                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / e_last

            else :
                kap_neu.append(kap_alt)
                last_neu.append(alt)
                soc.append(r_soc)
                
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / e_last
        else:
            if c_time >= a_laden and e_laden >= c_time:
                dif_kap = max_kap - kap_alt
                ew = min(l_last, abs(alt))
                ew = min(ew, dif_kap * 4)

                last_neu.append(alt + ew)
                kap_neu.append(kap_alt + (ew / 4))
                soc.append((kap_neu[-1]/max_kap) * 100)

                r_soc = soc[-1]
                kap_alt = kap_neu[-1]

                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / e_last

            else:
                last_neu.append(alt)
                kap_neu.append(kap_alt)
                soc.append(r_soc)

                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / e_last

        last_alt_dict[c_t] = alt
        l_last_dict[c_t] = l_last
        kap_alt_dict[c_t] = kap_alt
        e_last_dict[c_t] = e_last

        last_bat[c_t] = last_neu[-1]
        except_bat[c_t] = kap_alt / e_last


    return  time_array, last_alt, last_neu, kap_neu, soc

def modelC(table, cur_model):
    global last_bat
    global except_bat
    last_bat.clear()
    except_bat.clear()
    last_alt_dict.clear()
    kap_alt_dict.clear()
    l_last_dict.clear()
    # 结果列表
    last_alt = list()
    last_neu = list()
    soc = list()

    # 中间变量
    kap_neu = list()

    # 时间列
    time_array = []
    time_array.extend(transToTime(table.col_values(0)[1:]))    

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    if len(obj) == 0:
        return time_array, last_alt, last_neu, kap_neu, soc

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率
    a_laden = obj[0].a_laden
    e_laden = obj[0].e_laden
    a_entladen = obj[0].a_entladen
    e_entladen = obj[0].e_entladen
    p_p = obj[0].percent_power

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')

    # 计算列表最小值
    min_kw = min(col02[2:])

    # 电价列
    col03 = table.col_values(3)

    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()

    r_soc = 0
    for alt, c_t in zip(last_alt, time_array[1:]):
        if alt > 0: # last_alt大于0的情况

            if kap_alt == 0: # 当前电池电量为零的情况

                kap_neu.append(0)
                soc.append(0)
                last_neu.append(alt)
                r_soc = 0

            else:
                # 求最小值
                ew = min(e_last, alt)
                ew = min(ew, kap_alt * 4)
                # if ew > kap_alt * 4:
                #     ew = kap_alt

                # 保存计算结果
                last_neu.append(alt - ew)
                kap_neu.append(kap_alt - ew / 4)
                soc.append(((kap_alt - ew) / max_kap) * 100)
                kap_alt = ((kap_alt - ew / 4))
                r_soc = soc[-1]

        else:# last_alt 小于0的情况

            if abs(alt) > p_p:
                last_neu.append(alt)
                kap_neu.append(kap_alt)
                soc.append(r_soc)
                kap_alt = kap_neu[-1]

            else:
                diff_last = p_p - abs(alt)
                dif_kap = max_kap - kap_alt
                ew = min(l_last, diff_last)
                ew = min(ew, dif_kap * 4)
                
                last_neu.append(alt + ew)
                kap_neu.append(kap_alt + (ew / 4))
                soc.append((kap_neu[-1] / max_kap) * 100)

                kap_alt = kap_neu[-1]
                r_soc = soc[-1]
        
        last_bat[c_t] = last_neu[-1]
        except_bat[c_t] = kap_alt / e_last
        last_alt_dict[c_t] = alt
        l_last_dict[c_t] = l_last
        kap_alt_dict[c_t] = kap_alt
        e_last_dict[c_t] = e_last

    return time_array, last_alt, last_neu, kap_neu, soc

def modelD(table, cur_model):
    global last_bat
    global except_bat
    last_bat.clear()
    except_bat.clear()
    last_alt_dict.clear()
    kap_alt_dict.clear()
    l_last_dict.clear()    
    print("run model D")
    # 结果列表
    last_alt = list()
    last_neu = list()
    soc = list()

    # 中间变量
    kap_neu = list()

    # 时间列
    time_array = []
    time_array.extend(transToTime(table.col_values(0)[1:]))    

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    if len(obj) == 0:
        return time_array, last_alt, last_neu, kap_neu, soc

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率
    a_laden = obj[0].a_laden
    e_laden = obj[0].e_laden
    a_entladen = obj[0].a_entladen
    e_entladen = obj[0].e_entladen

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')

    # 电价列
    col03 = table.col_values(3)

    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()

    r_soc = 0
    for alt, c_t in zip(last_alt, time_array[1:]):
        c_time = datetime.strptime(c_t,'%H:%M:%S').time()

        if alt > 0:
            if c_time >= a_entladen and e_entladen >= c_time:
                if kap_alt == 0: # 当前电池电量为零的情况

                    kap_neu.append(0)
                    soc.append(0)
                    last_neu.append(alt)
                    r_soc = 0

                else:
                    # 求最小值
                    ew = min(e_last, alt)
                    ew = min(ew, kap_alt * 4)

                    # 保存计算结果
                    last_neu.append(alt - ew)
                    kap_neu.append(kap_alt - ew / 4)
                    soc.append(((kap_alt - ew) / max_kap) * 100)
                    kap_alt = ((kap_alt - ew / 4))

                    r_soc = soc[-1]

            else:
                kap_neu.append(0)
                soc.append(r_soc)
                last_neu.append(alt)
                kap_alt = 0

        else:
            if c_time >= a_laden and e_laden >= c_time:
                if kap_alt == max_kap: # kap_alt 到达最大值的情况
                    # 保存计算结果
                    last_neu.append(alt)
                    kap_neu.append(max_kap)
                    soc.append(100.0)
                    
                    # 更新当前电量
                    kap_alt = max_kap
                    r_soc = soc[-1]

                else:
                    # 计算最小值
                    dif_kap = max_kap - kap_alt
                    ew = min(abs(alt), dif_kap * 4.0)
                    ew = min(ew, l_last)

                    # 保存计算结果
                    last_neu.append(alt + ew)
                    kap_neu.append(kap_alt + (ew / 4))
                    soc.append(((kap_alt + (ew / 4)) / max_kap) * 100)
                    
                    # 更新当前电量
                    kap_alt = ((kap_alt + (ew / 4)))
                    r_soc = soc[-1]

            else:
                last_neu.append(alt)
                kap_neu.append(kap_alt)
                soc.append(r_soc)

        last_bat[c_t] = last_neu[-1]
        except_bat[c_t] = kap_alt / e_last
        last_alt_dict[c_t] = alt
        l_last_dict[c_t] = l_last
        kap_alt_dict[c_t] = kap_alt
        e_last_dict[c_t] = e_last


    return time_array, last_alt, last_neu, kap_neu, soc

def modelE(table, cur_model):
    global last_bat
    global except_bat
    last_bat.clear()
    except_bat.clear()
    last_alt_dict.clear()
    kap_alt_dict.clear()
    l_last_dict.clear()    
    # 结果列表
    last_alt = list()
    last_neu = list()
    soc = list()

    # 中间变量
    kap_neu = list()

    # 时间列
    time_array = []
    time_array.extend(transToTime(table.col_values(0)[1:]))    

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    if len(obj) == 0:
        return time_array, last_alt, last_neu, kap_neu, soc

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率
    a_laden = obj[0].a_laden
    e_laden = obj[0].e_laden
    a_entladen = obj[0].a_entladen
    e_entladen = obj[0].e_entladen
    p_p = obj[0].percent_power

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')

    # 电价列
    col03 = table.col_values(3)

    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()

    r_soc = 0
    for alt, c_t in zip(last_alt, time_array[1:]):
        c_time = datetime.strptime(c_t,'%H:%M:%S').time()
        if alt > 0: # last_alt大于0的情况

            if c_time >= a_entladen and e_entladen >= c_time:
                if kap_alt == 0: # 当前电池电量为零的情况

                    kap_neu.append(0)
                    soc.append(0)
                    last_neu.append(alt)
                    r_soc = 0

                else:
                    # 求最小值
                    ew = min(e_last, alt)
                    ew = min(ew, kap_alt * 4)

                    # 保存计算结果
                    last_neu.append(alt - ew)
                    kap_neu.append(kap_alt - ew / 4)
                    soc.append(((kap_alt - ew) / max_kap) * 100)
                    kap_alt = ((kap_alt - ew / 4))

                    r_soc = soc[-1]

            else:
                kap_neu.append(0)
                soc.append(r_soc)
                last_neu.append(alt)
                kap_alt = 0
                
        else:# last_alt 小于0的情况
            if c_time >= a_laden and e_laden >= c_time:
                if abs(alt) > p_p:
                    last_neu.append(alt)
                    kap_neu.append(kap_alt)
                    soc.append(r_soc)
                    kap_alt = kap_neu[-1]

                else:
                    diff_last = p_p - abs(alt)
                    dif_kap = max_kap - kap_alt
                    ew = min(l_last, diff_last)
                    ew = min(ew, dif_kap * 4)
                    
                    last_neu.append(alt + ew)
                    kap_neu.append(kap_alt + (ew / 4))
                    soc.append((kap_neu[-1] / max_kap) * 100)

                    kap_alt = kap_neu[-1]
                    r_soc = soc[-1]

            else:
                last_neu.append(alt)
                kap_neu.append(kap_alt)
                soc.append(r_soc)
                kap_alt = kap_neu[-1]

        last_bat[c_t] = last_neu[-1]
        except_bat[c_t] = kap_alt / e_last
        last_alt_dict[c_t] = alt
        l_last_dict[c_t] = l_last
        kap_alt_dict[c_t] = kap_alt
        e_last_dict[c_t] = e_last


    return time_array, last_alt, last_neu, kap_neu, soc

def modelF(table, cur_model):
    global last_bat
    global except_bat
    last_bat.clear()
    except_bat.clear()
    last_alt_dict.clear()
    kap_alt_dict.clear()
    l_last_dict.clear()    
    # 结果列表
    last_alt = list()
    last_neu = list()
    soc = list()

    # 中间变量
    kap_neu = list()

    # 时间列
    time_array = []
    time_array.extend(transToTime(table.col_values(0)[1:]))    

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    if len(obj) == 0:
        return time_array, last_alt, last_neu, kap_neu, soc

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率
    a_laden = obj[0].a_laden
    e_laden = obj[0].e_laden
    a_entladen = obj[0].a_entladen
    e_entladen = obj[0].e_entladen
    p_p = obj[0].percent_power
    net = obj[0].netzentlastang

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')

    # 电价列
    col03 = table.col_values(3)

    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()

    r_soc = 0
    for alt, c_t in zip(last_alt, time_array[1:]):
        c_time = datetime.strptime(c_t,'%H:%M:%S').time()

        if alt > 0:
            if kap_alt == 0: # 当前电池电量为零的情况

                kap_neu.append(0)
                soc.append(0)
                last_neu.append(alt)
                r_soc = (soc[-1])
                kap_alt = kap_neu[-1]

            else:
                # 求最小值
                ew = min(e_last, alt)
                ew = min(ew, kap_alt * 4)
                # if ew > kap_alt * 4:
                #     ew = kap_alt

                # 保存计算结果
                last_neu.append(alt - ew)
                kap_neu.append(kap_alt - ew / 4)
                soc.append(((kap_alt - ew) / max_kap) * 100)
                kap_alt = ((kap_alt - ew / 4))
                r_soc = (soc[-1])

        else:
            if kap_alt == max_kap:
                kap_neu.append(kap_alt)
                soc.append(100)
                last_neu.append(alt)
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]

            else:
                last_red = abs(alt * net)
                dif_kap = max_kap - kap_alt
                ew = min(l_last, dif_kap * 4)
                ew = min(ew, last_red)
                last_neu.append(alt + ew)
                kap_neu.append(kap_alt + (ew / 4))
                soc.append((kap_neu[-1] / max_kap) * 100)
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]

        last_bat[c_t] = last_neu[-1]
        except_bat[c_t] = kap_alt / e_last
        last_alt_dict[c_t] = alt
        l_last_dict[c_t] = l_last
        kap_alt_dict[c_t] = kap_alt
        e_last_dict[c_t] = e_last

    return time_array, last_alt, last_neu, kap_neu, soc


def procData(model, excel, cur_model):

    # 初始化 GPIO
    initGPIO()

    jsonRes = []
    print(excel)
    if(len(excel) == 0):
        return jsonRes

    # 加载 excel 表格数据
    item = get_object_or_404(ExcelFile, filename=excel)
    data = xlrd.open_workbook(os.path.join(
        MEDIA_ROOT + '/'+str(item.excelfile)))
    table = data.sheet_by_name(str(data.sheet_names()[0]))


    time_array, last_alt, last_neu, kap_neu, soc = createList()

    print('current model:', cur_model)
    
    if cur_model == 'modelA':
        time_array, last_alt, last_neu, kap_neu, soc = modelA(table, cur_model)

    elif cur_model == 'modelB':
        time_array, last_alt, last_neu, kap_neu, soc = modelB(table, cur_model)

    elif cur_model == 'modelC':
        time_array, last_alt, last_neu, kap_neu, soc = modelC(table, cur_model)

    elif cur_model == 'modelD':
        time_array, last_alt, last_neu, kap_neu, soc = modelD(table, cur_model)

    elif cur_model == 'modelE':
        time_array, last_alt, last_neu, kap_neu, soc = modelE(table, cur_model)

    elif cur_model == 'modelF':
        time_array, last_alt, last_neu, kap_neu, soc = modelF(table, cur_model)





    last_alt.insert(0, 'line')
    last_alt.insert(1, 'Last_alt')

    last_neu.insert(0, 'line')
    last_neu.insert(1, 'last_neu')

    kap_neu.insert(0, 'line')
    kap_neu.insert(1, 'kap_neu')


    soc = np.array(soc) * 0.01
    soc = soc.tolist()
    soc.insert(0, 'line')
    soc.insert(1, 'soc')

    jsonRes = [time_array, last_neu, last_alt, soc]

    return jsonRes



def pwmModelA(cur_model, time):
    global last_bat
    global except_bat
    global last_alt_dict # 新负载
    global kap_alt_dict  # 当前电池电量
    global l_last_dict   # 充电功率
    global polor_dict
    global e_last_dict

    last_alt = last_alt_dict[time]
    kap_alt = kap_alt_dict[time]
    e_last = e_last_dict[time]
    l_last = l_last_dict[time]

    #last_alt = -0.5
    #l_last = 1
    #e_last = 1

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    max_kap = obj[0].max_bat # 最大电池电量

    bat_time = 0
    charge_time = 0
    
    pwm2Bat = 0
    pwm2PoNet = 0
    pwm2Dev = 0
    
    if last_alt > 0:
        print("电网供电")
        if kap_alt != 0:
            print("电池送电到用电器")

            if last_alt < e_last:
                pwm2Dev = last_alt / e_last

            if e_last <= last_alt:
                pwm2Dev = 1

            if last_alt < e_last:
                bat_time = kap_alt / last_alt
            else:
                bat_time = kap_alt / e_last


    else:
        print("太阳能送电到电网")

        if kap_alt != max_kap:
            print("太阳能送电到电池")

            if abs(last_alt) < l_last:
                pwm2Bat = 1
            
            if abs(last_alt) > l_last:
                pwm2Bat = l_last / abs(last_alt)
                print("太阳能到电网打开")
                pwm2PoNet = (abs(last_alt) - l_last) / abs(last_alt)

            dif_kap = max_kap - kap_alt

            if abs(last_alt) < l_last:
                charge_time = dif_kap / abs(last_alt)

            else:    
                charge_time = dif_kap / l_last

    print("pwm2Bat: ", pwm2Bat, " pwm2PoNet: ", pwm2PoNet, " pwm2Dev: ", pwm2Dev)
    print("bat time: ", bat_time, " charge time: ", charge_time)

    runCh1(pwm2Bat * 100)
    runCh2(pwm2PoNet * 100)
    runCh3(pwm2Dev * 100)
    # runCh4(pwm2Bat * 100)

    return bat_time


def pwmModelB(cur_model, time):
    global last_bat
    global except_bat
    global last_alt_dict # 新负载
    global kap_alt_dict  # 当前电池电量
    global l_last_dict   # 充电功率
    global polor_dict
    global e_last_dict

    last_alt = last_alt_dict[time]
    kap_alt = kap_alt_dict[time]
    e_last = e_last_dict[time]
    l_last = l_last_dict[time]

    last_alt = -1
    l_last = 1

    if(len(last_alt_dict) == 0):
        return

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    max_kap = obj[0].max_bat # 最大电池电量

    bat_time = 0
    
    pwm2Bat = 0
    pwm2PoNet = 0
    pwm2Dev = 0
    
    if last_alt > 0:
        print("电网供电")
        if kap_alt != 0:
            print("电池送电到用电器")

            if last_alt < e_last:
                pwm2Dev = last_alt / e_last

            if e_last <= last_alt:
                pwm2Dev = 1

            if last_alt < e_last:
                bat_time = kap_alt / last_alt
            else:
                bat_time = kap_alt / e_last


    else:
        print("太阳能送电到电网")

        if kap_alt != max_kap:
            print("太阳能送电到电池")

            if abs(last_alt) < l_last:
                pwm2Bat = 1
            
            if abs(last_alt) > l_last:
                pwm2Bat = l_last / abs(last_alt)
                print("太阳能到电网打开")
                pwm2PoNet = (abs(last_alt) - l_last) / abs(last_alt)

            dif_kap = max_kap - kap_alt

            if abs(last_alt) < l_last:
                bat_time = dif_kap / abs(last_alt)

            else:    
                bat_time = dif_kap / l_last

    print("pwm2Bat: ", pwm2Bat, " pwm2PoNet: ", pwm2PoNet, " pwm2Dev: ", pwm2Dev, " bat time: ", bat_time)

    return bat_time

def pwmModelC(cur_model, time):
    pass

def pwmModelD(cur_model, time):
    pass

def pwmModelE(cur_model, time):
    pass

def pwmModelF(cur_model, time):
    pass

def procPWMOutput(cur_model, time):
    print('current model:', cur_model)

    if(len(last_alt_dict) == 0):
        return
    
    if cur_model == 'modelA':
        return pwmModelA(cur_model, time)

    elif cur_model == 'modelB':
        return pwmModelB(cur_model, time)

    elif cur_model == 'modelC':
        return pwmModelC(cur_model, time)

    elif cur_model == 'modelD':
        return pwmModelD(cur_model, time)

    elif cur_model == 'modelE':
        return pwmModelE(cur_model, time)

    elif cur_model == 'modelF':
        return pwmModelF(cur_model, time)





def procBtn(btn):

    global btnList
    print('btn is: ', btn)

    for i in range(len(btnList)):
        if btnList[i]['id'] == btn:
            btnList[i]['status'] = not btnList[i]['status']
            break

    print('index: ', i)
    res = dict()
    res['btn'] = btn
    res['status'] = btnList[i]['status']

    return res


def transToTime(array):
    time_arr = []
    for i in array:
        m = (int)(i * 24 * 3600)
        time_arr.append(time((int)(m / 3600), (int)((m%3600)/ 60), m%60).strftime('%H:%M:%S'))

    return time_arr


def timerRun(inc):

    time = datetime.now()
    min = time.minute
    if(min % 15 == 0):
        print('timer is running', time)

        timeStr = time.strftime("%H:%M:00")
        procPWMOutput(currentParamSetModel, timeStr)

    t = Timer(inc, timerRun, (inc,))
    t.start()

timerRun(60)
