#改版本第一次，加入full_bat.
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
full_bat = dict()
last_alt_dict = dict() # 新负载
a_preis_dict= dict() #电价
kap_alt_dict = dict()  # 当前电池电量
l_last_dict = dict()   # 充电功率
polor_dict = dict()
preis_dict = dict()
e_last_dict = dict()


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
#Maximierung des Eigenverbrauchs
# 初始化字典
    global last_bat
    global except_bat
    global full_bat
    last_bat.clear()
    except_bat.clear()
    full_bat.clear()
    
    # 结果列表
    last_alt = list() # 新负载
    last_neu = list() # 新电量
    soc = list()      # 电池电量

    # 中间变量
    kap_neu = list()
    dif_kap=0

    # 时间_数组
    time_array = list() # []列表 {}字典
    time_array.extend(transToTime(table.col_values(0)[1:]))    
    #读取了时间列
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

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()#last_lat是一个数列，不是字典

    r_soc = kap_alt/max_kap#表示算出的当前电量百分比#这两个值来源于输入
    for alt, c_t in zip(last_alt, time_array):#打包了两个数列
         
        if alt > 0: # last_alt大于0的情况,考虑电池的放电

            if kap_alt == 0: # 当前电池电量为零的情况，取旧值
                #输出成图
                kap_neu.append(0)
                soc.append(r_soc)
                last_neu.append(alt)

                #输出成单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0
                #更新电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]

            else:# 当前电池有电的情况，考虑电池放电
                # 求最小值
                ew = min(e_last, alt)
                ew = min(ew, kap_alt * 4)

                # 保存计算结果
                last_neu.append(alt - ew)#电网供电减少
                kap_neu.append(kap_alt - ew / 4)#电池放电
                soc.append(((kap_alt - ew / 4) / max_kap) * 100)#电池电量百分比
                # 更新当前电量
                kap_alt = ((kap_alt - ew / 4))
                r_soc = soc[-1]

                 #输出到单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / ew
                full_bat[c_t] = 0

        else:# last_alt 小于0的情况,太阳能到电网，考虑给电池充电

            if kap_alt == max_kap: # kap_alt 到达最大值的情况，不考虑电池的影响
                # 取旧值
                last_neu.append(alt)
                kap_neu.append(max_kap)
                soc.append(100.0)
                
                # 更新当前电量
                kap_alt = max_kap

                #取旧值
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0

            else:#电池没有充满，给电池充电
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
                r_soc=r_soc = soc[-1]


                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = dif_kap/ew

        last_alt_dict[c_t] = alt
        #l_last_dict[c_t] = l_last
        #kap_alt_dict[c_t] = kap_alt
        #e_last_dict[c_t] = e_last

        # last_bat[c_t] = last_neu[-1]
        #except_bat[c_t] = kap_alt / e_last
        # full_bat[c_t] = dif_Kap/ew

    return time_array, last_alt, last_neu, kap_neu, soc

def modelB(table, cur_model):
#时间限制
    global last_bat
    global except_bat
    global full_bat
    last_bat.clear()
    except_bat.clear()
    full_bat.clear()
    last_alt_dict.clear()
    kap_alt_dict.clear()
    l_last_dict.clear()


    # 结果列表
    last_alt = list()
    last_neu = list()
    soc = list()

    # 中间变量
    kap_neu = list()
    dif_kap=0

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



    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()

    r_soc = kap_alt/max_kap#表示算出的当前电量百分比
    for alt, c_t in zip(last_alt, time_array[1:]):

        c_time = datetime.strptime(c_t,'%H:%M:%S').time()

        if alt > 0: # last_alt大于0的情况，电网供电给用电器,考虑电池的放电
            if c_time >= a_entladen and e_entladen >= c_time:#在放电时间段内
                if kap_alt == 0:
                    #当前电池电量为零的情况，取旧值
                    #输出成图
                    kap_neu.append(0)
                    soc.append(r_soc)
                    last_neu.append(alt)
                    #保存计算结果
                    r_soc = 0
                    kap_alt=kap_neu[-1]

                    #输出成单元格
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = 0
                else:#当前电池有电的情况，考虑电池放电
                    # 求最小值
                    ew = min(alt, kap_alt * 4)
                    ew = min(ew, e_last)

                    # 输出到图像
                    last_neu.append(alt - ew)#电网供电减少
                    kap_neu.append(kap_alt - (ew / 4))#电池放电
                    soc.append((kap_neu/max_kap) * 100)#电池电量百分比
                    #更新电池电量              
                    kap_alt = kap_neu[-1]
                    r_soc = soc[-1]

                    #输出到单元格部分
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] =0
                    full_bat[c_t]=0

            else :#时间在放电时间之外。取旧值
                #输出到图像
                kap_neu.append(kap_alt)
                last_neu.append(alt)
                soc.append(r_soc)
                #输出到格子
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t]=0
                #更新电池电量              
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]

        else:# last_alt 小于0的情况,太阳能到电网，考虑给电池充电            
            if c_time >= a_laden and e_laden >= c_time:#在充电时间内
                if kap_alt == max_kap: # kap_alt 到达最大值的情况，不考虑电池的影响
                    # 取旧值
                    last_neu.append(alt)
                    kap_neu.append(max_kap)
                    soc.append(100.0)
                    
                    # 更新当前电量
                    kap_alt = max_kap

                    #取旧值
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = 0
                    
                else :#电池没有充满，给电池充电
                    dif_kap = max_kap - kap_alt
                    ew = min(abs(alt), dif_kap * 4.0)
                    ew = min(ew, l_last)

                    # 保存计算结果
                    last_neu.append(alt + ew)
                    kap_neu.append(kap_alt + (ew / 4))
                    soc.append(((kap_alt + (ew / 4)) / max_kap) * 100)
                
                    # 更新当前电量
                    kap_alt = ((kap_alt + (ew / 4)))
                    r_soc=r_soc = soc[-1]


                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = dif_kap/ew     
           
            else:#在充电时间外，取旧值
                last_neu.append(alt)
                kap_neu.append(kap_alt)
                soc.append(r_soc)

                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat=0


        last_alt_dict[c_t] = alt
        #l_last_dict[c_t] = l_last
        #kap_alt_dict[c_t] = kap_alt
        #e_last_dict[c_t] = e_last

        #last_bat[c_t] = last_neu[-1]
        #except_bat[c_t] = kap_alt / e_last


    return time_array, last_alt, last_neu, kap_neu, soc, except_bat, full_bat, last_bat

def modelC(table, cur_model):
    #限制
    global last_bat
    global except_bat
    global full_bat
    last_bat.clear()
    except_bat.clear()
    full_bat.clear()
    last_alt_dict.clear()
    kap_alt_dict.clear()
    l_last_dict.clear()
    print("run model C")
    # 结果列表
    last_alt = list()
    last_neu = list()
    soc = list()

    # 中间变量
    kap_neu = list()
    dif_last=0
    dif_kap=0
    

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

    p_p = obj[0].percent_power

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')

    # 计算列表最小值
    #min_kw = min(col02[2:])



    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()
    AB=abs(min(last_alt))*p_p
    dif_last=abs(min(last_alt))-AB

    r_soc = kap_alt/max_kap#表示算出的当前电量百分比
    for alt, c_t in zip(last_alt, time_array[1:]):
        if alt > 0: # 电网供电给用电器,考虑电池的放电，同模式A

            if kap_alt == 0: # 当前电池电量为零的情况，取旧值

                #输出成图
                kap_neu.append(0)
                soc.append(r_soc)
                last_neu.append(alt)
                #输出成单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0               


            else:#电池有电，电池放电
                # 求最小值             
                
                ew = min(e_last, alt)
                ew = min(ew, kap_alt * 4)
                   
              
                # 保存计算结果
                last_neu.append(alt - ew)
                kap_neu.append(kap_alt - ew / 4)
                soc.append(((kap_alt - ew) / max_kap) * 100)

                kap_alt = ((kap_alt - ew / 4))
                r_soc = soc[-1]

                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / ew
                full_bat[c_t] = 0

        else:
            # last_alt 小于0的情况,太阳能到电网，考虑给电池充电
            if abs(alt) > AB and max_kap!=kap_alt:#超过界限，给电池充电
                 #diff_last = AB - abs(alt)
                dif_kap = max_kap - kap_alt
                ew = min(l_last, dif_last)
                ew = min(ew, dif_kap * 4)
                
                last_neu.append(alt + ew)
                kap_neu.append(kap_alt + (ew / 4))
                soc.append((kap_neu[-1] / max_kap) * 100)

                #更新电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]
                #选时间，输出充满和放电时间估计
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = dif_kap/ew
                     
            else:#没有超过限制
                #取旧值
                last_neu.append(alt)
                kap_neu.append(kap_alt)
                soc.append(r_soc)
                #更新电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]                
                #选时间，给输出，输出结果是电网新的供电，预计电池充满和放电时间
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0
                
        #last_bat[c_t] = last_neu[-1]
        #except_bat[c_t] = kap_alt / e_last
        last_alt_dict[c_t] = alt
        #l_last_dict[c_t] = l_last
        #kap_alt_dict[c_t] = kap_alt
        #e_last_dict[c_t] = e_last

    
    return time_array, last_alt, last_neu, kap_neu, soc

def modelD(table, cur_model):
    #时间加限制
    global last_bat
    global except_bat
    global full_bat
    last_bat.clear()
    except_bat.clear()
    full_bat.clear()
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
    p_p = obj[0].percent_power

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')



    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()
    AB=abs(min(last_alt))*p_p
    dif_last=abs(min(last_alt))-AB

    r_soc = kap_alt/max_kap#表示算出的当前电量百分比
    for alt, c_t in zip(last_alt, time_array[1:]):
        c_time = datetime.strptime(c_t,'%H:%M:%S').time()

        if alt > 0:#同模式B alt > 0
            if c_time >= a_entladen and e_entladen >= c_time:#在放电时间段内
                if kap_alt == 0: 
                    # 当前电池电量为零的情况
                    #输出成图像
                    kap_neu.append(0)
                    soc.append(r_soc)
                    last_neu.append(alt)
                    #保存计算结果
                    r_soc = 0
                    kap_alt=kap_neu[-1]

                    #输出成单元格
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = 0

                else:#当前电池有电的情况，考虑电池放电
                    # 求最小值
                    ew = min(e_last, alt)
                    ew = min(ew, kap_alt * 4)

                    # 输出到图像
                    last_neu.append(alt - ew)
                    kap_neu.append(kap_alt - ew / 4)
                    soc.append(((kap_alt - ew) / max_kap) * 100)
                    kap_alt = ((kap_alt - ew / 4))

                    r_soc = soc[-1]          

        else:# last_alt 小于0的情况,太阳能到电网，考虑给电池充电
            if c_time >= a_laden and e_laden >= c_time:
                #在充电时间内，同方案C last_alt 小于0
                if abs(alt) > AB and max_kap!=kap_alt:#超过界限，给电池充电
                    #diff_last = AB - abs(alt)
                    dif_kap = max_kap - kap_alt
                    ew = min(l_last, dif_last)
                    ew = min(ew, dif_kap * 4)
                    
                    last_neu.append(alt + ew)
                    kap_neu.append(kap_alt + (ew / 4))
                    soc.append((kap_neu[-1] / max_kap) * 100)

                    #更新电量
                    kap_alt = kap_neu[-1]
                    r_soc = soc[-1]
                    #选时间，输出充满和放电时间估计,输出到格子
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = dif_kap/ew
                        
                else:#没有超过限制
                    #取旧值
                    last_neu.append(alt)
                    kap_neu.append(kap_alt)
                    soc.append(r_soc)
                    #更新电量
                    kap_alt = kap_neu[-1]
                    r_soc = soc[-1]                
                    #选时间，给输出，输出结果是电网新的供电，预计电池充满和放电时间
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = 0

            else:#在充电时间之外，取旧值
                #取旧值
                last_neu.append(alt)
                kap_neu.append(kap_alt)
                soc.append(r_soc)
                #更新电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]                
                #选时间，给输出，输出结果是电网新的供电，预计电池充满和放电时间
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0

        #last_bat[c_t] = last_neu[-1]
        #except_bat[c_t] = kap_alt / e_last
        last_alt_dict[c_t] = alt
        #l_last_dict[c_t] = l_last
        #kap_alt_dict[c_t] = kap_alt
        #e_last_dict[c_t] = e_last


    return time_array, last_alt, last_neu, kap_neu, soc


def modelE(table, cur_model):
    #缓解百分比
    global last_bat
    global except_bat
    global full_bat
    last_bat.clear()
    except_bat.clear()
    full_bat.clear()
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
    dif_kap=0

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

    net = obj[0].netzentlastang

    # 功率列
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')



    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()

    r_soc = kap_alt/max_kap#表示算出的当前电量百分比
    for alt, c_t in zip(last_alt, time_array[1:]):


        if alt > 0:#同方案ALast_alt>0
             # last_alt大于0的情况,考虑电池的放电
            if kap_alt == 0: # 当前电池电量为零的情况，取旧值

                #输出成图
                kap_neu.append(0)
                soc.append(r_soc)
                last_neu.append(alt)

                #输出成单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0
                #更新电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]

            else:# 当前电池有电的情况，考虑电池放电
                # 求最小值
                ew = min(e_last, alt)
                ew = min(ew, kap_alt * 4)
               

                # 保存计算结果
                last_neu.append(alt - ew)#电网供电减少
                kap_neu.append(kap_alt - ew / 4)#电池放电
                soc.append(((kap_alt - ew) / max_kap) * 100)
                #电池电量百分比
                # 更新当前电量
                kap_alt = ((kap_alt - ew / 4))
                r_soc = (soc[-1])
                #输出到单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = kap_alt / ew
                full_bat[c_t] = 0


        else:# last_alt 小于0的情况,太阳能到电网，考虑给电池充电
            if kap_alt == max_kap:#充满不再充电
                kap_neu.append(kap_alt)
                soc.append(100)
                last_neu.append(alt)
                # 更新当前电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]
                #输出到单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0

            else:#没充满
                last_red = abs(alt * net)
                dif_kap = max_kap - kap_alt
                ew = min(l_last, dif_kap * 4)
                ew = min(ew, last_red)
                last_neu.append(alt + ew)
                kap_neu.append(kap_alt + (ew / 4))
                soc.append((kap_neu[-1] / max_kap) * 100)
                # 更新当前电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]
                #输出到单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = dif_kap/ew

        #last_bat[c_t] = last_neu[-1]
        #except_bat[c_t] = kap_alt / e_last
        last_alt_dict[c_t] = alt
        #l_last_dict[c_t] = l_last
        #kap_alt_dict[c_t] = kap_alt
        #e_last_dict[c_t] = e_last

    return time_array, last_alt, last_neu, kap_neu, soc

def modelF(table, cur_model):
    #电价
    global last_bat
    global except_bat
    global full_bat
    last_bat.clear()
    except_bat.clear()
    full_bat.clear()
    last_alt_dict.clear()    
    kap_alt_dict.clear()
    l_last_dict.clear()    
    print("run model F")
    # 结果列表
    last_alt = list()
    last_neu = list()
    soc = list()

    # 中间变量
    kap_neu = list()
    dif_kap=0

    # 时间列
    time_array = []#时间数组
    time_array.extend(transToTime(table.col_values(0)[1:])) 

    #电价列
    preis_arry=[]
    preis_arry.extend(table.col_values(3)[1:])

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)
    #如果没有参数，不进行计算
    if len(obj) == 0:
        return time_array, last_alt, last_neu, kap_neu, soc

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率

    #net = obj[0].netzentlastang
    e_preis = obj[0].e_preis
    l_preis = obj[0].l_preis

    # 功率列，获取第二列的整列内容
    col01 = table.col_values(1)
    col01.insert(0, 'area')

    # 太阳能电量
    col02 = table.col_values(2)
    col02.insert(0, 'line')

    # 电价列
    col03 = table.col_values(3)
    col03.insert(0, 'line')

    #时间和太阳能的字典
    polor_dict.clear()
    for t, p in zip(time_array, col02[2:]):
        polor_dict[t] = p
    

    # 计算 last_alt
    a01 = (np.array(col01[2:]))
    a02 = (np.array(col02[2:]))
    array_last_alt = a01 + a02
    last_alt = array_last_alt.tolist()
    
    r_soc = kap_alt/max_kap#表示算出的当前电量百分比
    for alt, c_t, preis in zip(last_alt, time_array,preis_arry):
        
        a_preis=preis

        if alt > 0:# last_alt大于0的情况,考虑电池的放电
            if e_preis>a_preis:#市场价过高，不应该从电网取电么？
                #同方案A Last_alt>0
                # last_alt大于0的情况,考虑电池的放电
                if kap_alt == 0: # 当前电池电量为零的情况，取旧值
                    #输出成图
                    kap_neu.append(0)
                    soc.append(0)
                    last_neu.append(alt)

                    #输出成单元格
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = 0
                    #更新电量
                    kap_alt = kap_neu[-1]
                    r_soc = soc[-1]

                else:# 当前电池有电的情况，考虑电池放电
                    # 求最小值
                    ew = min(e_last, alt)
                    ew = min(ew, kap_alt * 4)

                    # 保存计算结果
                    last_neu.append(alt - ew)#电网供电减少
                    kap_neu.append(kap_alt - ew / 4)#电池放电
                    soc.append(((kap_alt - ew / 4) / max_kap) * 100)#电池电量百分比
                    # 更新当前电量
                    kap_alt = ((kap_alt - ew / 4))
                    r_soc = soc[-1]

                    #输出到单元格
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = kap_alt / ew
                    full_bat[c_t] = 0
            else:#市场价高，电网供电？
                kap_neu.append(kap_alt)
                soc.append(r_soc)
                last_neu.append(alt)

                #输出成单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0
                #更新电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]
        else:#last_alt<0,考虑电池充电。
            if l_preis>a_preis:#取旧值
                last_neu.append(alt)
                kap_neu.append(kap_alt)
                soc.append(r_soc)
                
                #输出成单元格
                last_bat[c_t] = last_neu[-1]
                except_bat[c_t] = 0
                full_bat[c_t] = 0
                #更新电量
                kap_alt = kap_neu[-1]
                r_soc = soc[-1]           
            else:#同方案A,Last_alt<0
                if kap_alt == max_kap: # kap_alt 到达最大值的情况，不考虑电池的影响
                    # 取旧值
                    last_neu.append(alt)
                    kap_neu.append(max_kap)
                    soc.append(100.0)
                    
                    # 更新当前电量
                    kap_alt = max_kap

                    #取旧值
                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = 0

                else:#电池没有充满，给电池充电
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
                    r_soc=r_soc = soc[-1]


                    last_bat[c_t] = last_neu[-1]
                    except_bat[c_t] = 0
                    full_bat[c_t] = dif_kap/ew
        last_alt_dict[c_t] = alt    
    return time_array, last_alt, last_neu, kap_neu, soc
                

def procData(model, excel, cur_model):

    # 初始化 GPIO
    initGPIO()
    #如果没有Excel就退出
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
    global last_alt_dict # 新负载
    global kap_alt_dict  # 当前电池电量
    global l_last_dict   # 充电功率
    global e_last_dict
    last_alt = last_alt_dict[time]
    kap_alt = kap_alt_dict[time]
    e_last = e_last_dict[time]
    l_last = l_last_dict[time]

    #last_alt = -0.5
    #l_last = 1
    #e_last = 1

    if(len(last_alt_dict) == 0):
        return

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率


   
    pwm2Bat = 0
    pwm2PoNet = 0
    pwm2Dev = 0
    
    if last_alt > 0: # last_alt大于0的情况,考虑电池的放电
        print("电网供电给用电器")
        if kap_alt != 0:# 当前电池有电的情况，考虑电池放电,取旧值的情况不需要控制。
            print("电池替代电网送电到用电器")
            #放电时候控制电路，不考虑电池的电量
            if last_alt < e_last:
                pwm2Bat = 0
                pwm2PoNet = 0
                pwm2Dev = last_alt / e_last                
                ew = min(e_last, kap_alt * 4)
                kap_alt = ((kap_alt - ew / 4))
                
            else:
                pwm2Bat = 0
                pwm2PoNet = 0
                pwm2Dev = 1
                ew = min(last_alt, kap_alt * 4)
                kap_alt = ((kap_alt - ew / 4))             


    else:# last_alt 小于0的情况,太阳能到电网，考虑给电池充电
        print("太阳能送电到电网")
        if kap_alt != max_kap:#电池没有充满才进行控制。
            print("太阳能2到电池")

            if abs(last_alt) < l_last:
                pwm2Bat = 1#太阳能全力给电池充电
                pwm2PoNet = 0#太阳能给的电满足电池，没有剩余，不给电网供电
                pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                dif_kap = max_kap - kap_alt              
                ew = min(abs(last_alt), dif_kap * 4.0)
                ew = min(ew, l_last)
                kap_alt = ((kap_alt + (ew / 4)))
            else:
                pwm2Bat = l_last / abs(last_alt)#太阳能一部分给电池
                print("太阳能2电网")
                pwm2PoNet = (abs(last_alt) - l_last) / abs(last_alt)#太阳能另一部分给电网
                pwm2Dev = 0#电池不需要给用电器供电
                dif_kap = max_kap - kap_alt
                ew = min(abs(last_alt), dif_kap * 4.0)
                ew = min(ew, l_last)
                kap_alt = ((kap_alt + (ew / 4)))
                

    print("pwm2Bat: ", pwm2Bat, " pwm2PoNet: ", pwm2PoNet, " pwm2Dev: ", pwm2Dev)
    

    runCh1(pwm2Bat * 100)
    runCh2(pwm2PoNet * 100)
    runCh3(pwm2Dev * 100)
    # runCh4(pwm2Bat * 100)

    return 


def pwmModelB(table,cur_model, time):   
    
    global last_alt_dict # 新负载
    global kap_alt_dict  # 当前电池电量
    global l_last_dict   # 充电功率
    global polor_dict
    global e_last_dict
    last_alt = last_alt_dict[time]
    kap_alt = kap_alt_dict[time]


    #last_alt = -1
    #l_last = 1

    if(len(last_alt_dict) == 0):
        return

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率
    a_laden = obj[0].a_laden
    e_laden = obj[0].e_laden
    a_entladen = obj[0].a_entladen
    e_entladen = obj[0].e_entladen

    time_array = []
    time_array.extend(transToTime(table.col_values(0)[1:]))   
    
    pwm2Bat = 0
    pwm2PoNet = 0
    pwm2Dev = 0
    c_t=time_array[1:]
    c_time = datetime.strptime(c_t,'%H:%M:%S').time()
    if last_alt > 0:# last_alt大于0的情况，电网供电给用电器,考虑电池的放电
        print("电网供电给用电器")
        if c_time >= a_entladen and e_entladen >= c_time:#在放电时间段内
            if kap_alt !=0:
                print("电池替代电网送电到用电器")   
                #放电时候控制电路，不考虑电池的电量 
  
                if last_alt < e_last:
                    pwm2Bat = 0
                    pwm2PoNet = 0
                    pwm2Dev = last_alt / e_last                
                    ew = min(e_last, kap_alt * 4)
                    kap_alt = ((kap_alt - ew / 4))
                    
                else:
                    pwm2Bat = 0
                    pwm2PoNet = 0
                    pwm2Dev = 1
                    ew = min(last_alt, kap_alt * 4)
                    kap_alt = ((kap_alt - ew / 4))             


    else:# last_alt 小于0的情况,太阳能到电网，考虑给电池充电
        print("太阳能送电到电网")
        if c_time >= a_laden and e_laden >= c_time:#在充电时间内
            if kap_alt != max_kap:
                print("太阳能2电池")

                if abs(last_alt) < l_last:
                    pwm2Bat = 1#太阳能全力给电池充电
                    pwm2PoNet = 0#太阳能给的电满足电池，没有剩余，不给电网供电
                    pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                    dif_kap = max_kap - kap_alt              
                    ew = min(abs(last_alt), dif_kap * 4.0)
                    ew = min(ew, l_last)
                    kap_alt = ((kap_alt + (ew / 4)))
                else:
                    pwm2Bat = l_last / abs(last_alt)#太阳能一部分给电池
                    print("太阳能2电网")
                    pwm2PoNet = (abs(last_alt) - l_last) / abs(last_alt)
                    pwm2Dev = 0#电池不需要给用电器供电
                    dif_kap = max_kap - kap_alt
                    ew = min(abs(last_alt), dif_kap * 4.0)
                    ew = min(ew, l_last)
                    kap_alt = ((kap_alt + (ew / 4)))

    print("pwm2Bat: ", pwm2Bat, " pwm2PoNet: ", pwm2PoNet, " pwm2Dev: ", pwm2Dev)
    runCh1(pwm2Bat * 100)
    runCh2(pwm2PoNet * 100)
    runCh3(pwm2Dev * 100)
    # runCh4(pwm2Bat * 100)

    return 

def pwmModelC(cur_model, time):
#限制
    global last_bat
    global except_bat
    global full_bat
    #global last_alt_dict # 新负载
    #global kap_alt_dict  # 当前电池电量
    #global l_last_dict   # 充电功率
    #global polor_dict #太阳能产生电量
    #global e_last_dict #放电功率

    last_alt = last_alt_dict[time]
    kap_alt = kap_alt_dict[time]
    e_last = e_last_dict[time]
    l_last = l_last_dict[time]

    #last_alt = -1
    #l_last = 1
    

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    if len(obj) == 0:
        return 

    max_kap = obj[0].max_bat # 最大电池电量
    p_p = obj[0].percent_power
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率


   

    AB=abs(min(last_alt))*p_p
    dif_last=abs(min(last_alt))-AB

    
    pwm2Bat = 0
    pwm2PoNet = 0
    pwm2Dev = 0
    

    if last_alt > 0:# last_alt大于0的情况，电网供电给用电器,考虑电池的放电
        print("电网供电给用电器")
        if kap_alt != 0:# 当前电池有电的情况，考虑电池放电,取旧值的情况不需要控制。
            print("电池替代电网送电到用电器")
            #放电时候控制电路，不考虑电池的电量
            if last_alt < e_last:
                pwm2Bat = 0
                pwm2PoNet = 0
                pwm2Dev = last_alt / e_last                
                ew = min(e_last, kap_alt * 4)
                kap_alt = ((kap_alt - ew / 4))
                
            else:
                pwm2Bat = 0
                pwm2PoNet = 0
                pwm2Dev = 1
                ew = min(last_alt, kap_alt * 4)
                kap_alt = ((kap_alt - ew / 4))             
    else:# last_alt 小于0的情况,太阳能到电网，考虑给电池充电
        if abs(last_alt) > AB and max_kap!=kap_alt:#超过界限，电池没充满，给电池充电
            print("太阳能2电池")
            if dif_last < l_last:
                pwm2Bat = dif_last/abs(min(last_alt))#太阳能超过限制部分给电池
                pwm2PoNet = AB/abs(min(last_alt))#太阳能按限制给电网供电
                pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                dif_kap = max_kap - kap_alt              
                ew = min(dif_last, dif_kap * 4.0)
                ew = min(ew, l_last)
                kap_alt = ((kap_alt + (ew / 4)))
            else:
                pwm2Bat = l_last/abs(min(last_alt))#太阳能超过限制部分给电池
                pwm2PoNet = (abs(min(last_alt))-l_last)/abs(min(last_alt))#太阳能按限制给电网供电
                pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                dif_kap = max_kap - kap_alt              
                ew = min(dif_last, dif_kap * 4.0)
                ew = min(ew, l_last)
                kap_alt = ((kap_alt + (ew / 4)))
               
    print("pwm2Bat: ", pwm2Bat, " pwm2PoNet: ", pwm2PoNet, " pwm2Dev: ", pwm2Dev)
    runCh1(pwm2Bat * 100)
    runCh2(pwm2PoNet * 100)
    runCh3(pwm2Dev * 100)
    # runCh4(pwm2Bat * 100)

    return 


            

def pwmModelD(cur_model, time):
    #限制+时间
    global last_alt_dict # 负载
    global kap_alt_dict  # 当前电池电量
    global l_last_dict   # 充电功率
    #global polor_dict #太阳能产生电量
    global e_last_dict #放电功率 
    last_alt = last_alt_dict[time]
    kap_alt = kap_alt_dict[time]
    e_last = e_last_dict[time]
    l_last = l_last_dict[time]

    if(len(last_alt_dict) == 0):
        return

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率
    p_p = obj[0].percent_power

    a_entladen = obj[0].a_entladen
    e_entladen = obj[0].e_entladen

    AB=abs(min(last_alt))*p_p
    dif_last=abs(min(last_alt))-AB
    
    pwm2Bat = 0
    pwm2PoNet = 0
    pwm2Dev = 0
    c_time =time
    if last_alt > 0:# last_alt大于0的情况，同方案B
        print("电网供电给用电器")
        if c_time >= a_entladen and e_entladen >= c_time:#在放电时间段内
            if kap_alt != 0:
                print("电池替代电网送电到用电器")   
                #放电时候控制电路，不考虑电池的电量 
  
                if last_alt < e_last:
                    pwm2Bat = 0
                    pwm2PoNet = 0
                    pwm2Dev = last_alt / e_last                
                    ew = min(e_last, kap_alt * 4)
                    kap_alt = ((kap_alt - ew / 4))
                    
                else:
                    pwm2Bat = 0
                    pwm2PoNet = 0
                    pwm2Dev = 1
                    ew = min(last_alt, kap_alt * 4)
                    kap_alt = ((kap_alt - ew / 4))
    else:#last_alt<0的情况，同方案C
        if abs(last_alt) > AB and max_kap!=kap_alt:#超过界限，电池没充满，给电池充电
            print("太阳能2电池")
            if dif_last < l_last:
                pwm2Bat = dif_last/abs(min(last_alt))#太阳能超过限制部分给电池
                pwm2PoNet = AB/abs(min(last_alt))#太阳能按限制给电网供电
                pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                dif_kap = max_kap - kap_alt              
                ew = min(dif_last, dif_kap * 4.0)
                ew = min(ew, l_last)
                kap_alt = ((kap_alt + (ew / 4)))
            else:
                pwm2Bat = l_last/abs(min(last_alt))#太阳能超过限制部分给电池
                pwm2PoNet = (abs(min(last_alt))-l_last)/abs(min(last_alt))#太阳能按限制给电网供电
                pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                dif_kap = max_kap - kap_alt              
                ew = min(dif_last, dif_kap * 4.0)
                ew = min(ew, l_last)
                kap_alt = ((kap_alt + (ew / 4)))
    
    print("pwm2Bat: ", pwm2Bat, " pwm2PoNet: ", pwm2PoNet, " pwm2Dev: ", pwm2Dev)
    runCh1(pwm2Bat * 100)
    runCh2(pwm2PoNet * 100)
    runCh3(pwm2Dev * 100)
    # runCh4(pwm2Bat * 100)

    return 


def pwmModelE(cur_model, time):
    #缓解百分比
    global last_alt_dict # 负载
    global kap_alt_dict  # 当前电池电量
    global l_last_dict   # 充电功率
    #global polor_dict #太阳能产生电量
    global e_last_dict #放电功率 
    last_alt = last_alt_dict[time]
    kap_alt = kap_alt_dict[time]
    e_last = e_last_dict[time]
    l_last = l_last_dict[time]

    if(len(last_alt_dict) == 0):
        return

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率

    a_entladen = obj[0].a_entladen
    e_entladen = obj[0].e_entladen
    net = obj[0].netzentlastang
    
    pwm2Bat = 0
    pwm2PoNet = 0
    pwm2Dev = 0
    last_red = abs(last_alt * net)
    dif_kap=0
    c_time=time

    if last_alt > 0:# last_alt大于0的情况，同方案A
        print("电网供电给用电器")
        if c_time >= a_entladen and e_entladen >= c_time:#在放电时间段内
            if kap_alt != 0:
                print("电池替代电网送电到用电器")   
                #放电时候控制电路，不考虑电池的电量 
  
                if last_alt < e_last:
                    pwm2Bat = 0
                    pwm2PoNet = 0
                    pwm2Dev = last_alt / e_last                
                    ew = min(e_last, kap_alt * 4)
                    kap_alt = ((kap_alt - ew / 4))
                    
                else:
                    pwm2Bat = 0
                    pwm2PoNet = 0
                    pwm2Dev = 1
                    ew = min(last_alt, kap_alt * 4)
                    kap_alt = ((kap_alt - ew / 4))

    else:#last_alt<0的情况
        if max_kap!=kap_alt:
            print("太阳能2电池")
            if last_red < l_last:
                pwm2Bat = net #太阳能超过限制部分给电池
                x=1-net
                pwm2PoNet = x #太阳能按限制给电网供电
                pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                dif_kap = max_kap - kap_alt              
                ew = min(last_red, dif_kap * 4.0)
                ew = min(ew, l_last)
                kap_alt = ((kap_alt + (ew / 4)))
            else:
                pwm2Bat = l_last/abs(last_alt) #太阳能超过限制部分给电池
                pwm2PoNet = (abs(last_alt)-l_last)/abs(last_alt)#太阳能按限制给电网供电
                pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                dif_kap = max_kap - kap_alt              
                ew = min(last_red, dif_kap * 4.0)
                ew = min(ew, l_last)
                kap_alt = ((kap_alt + (ew / 4)))

    print("pwm2Bat: ", pwm2Bat, " pwm2PoNet: ", pwm2PoNet, " pwm2Dev: ", pwm2Dev)
    runCh1(pwm2Bat * 100)
    runCh2(pwm2PoNet * 100)
    runCh3(pwm2Dev * 100)
    # runCh4(pwm2Bat * 100)

    return 

    
    

def pwmModelF(table,cur_model, time):
    #电价
    
    global last_alt_dict # 负载
    global a_preis_dict
    global kap_alt_dict  # 当前电池电量

    #global polor_dict #太阳能产生电量
    # 电价列
    col03 = table.col_values(3)
    col03.insert(0, 'line')
    last_alt = last_alt_dict[time]
    time_array = []#时间数组
    time_array.extend(transToTime(table.col_values(0)[1:])) 


    a_preis_dict.clear()
    for t, p in zip(time_array, col03[2:]):
        a_preis_dict[t] = p
   
    a_preis=a_preis_dict[time]

    if(len(last_alt_dict) == 0):
        return

    # 输入参数
    obj = InputParams.objects.filter(model_type = cur_model)

    max_kap = obj[0].max_bat # 最大电池电量
    kap_alt = obj[0].cur_bat # 当前电池电量
    l_last =  obj[0].charge_bat # 充电功率
    e_last =  obj[0].run_bat # 运行功率

    e_preis = obj[0].e_preis
    l_preis = obj[0].l_preis
    
    pwm2Bat = 0
    pwm2PoNet = 0
    pwm2Dev = 0
   
    if last_alt > 0:# last_alt大于0的情况
        if e_preis>a_preis:#同方案A
            print("电网供电给用电器")
            if kap_alt != 0:# 当前电池有电的情况，考虑电池放电,取旧值的情况不需要控制。
                print("电池替代电网送电到用电器")
                #放电时候控制电路，不考虑电池的电量
                if last_alt < e_last:
                    pwm2Bat = 0
                    pwm2PoNet = 0
                    pwm2Dev = last_alt / e_last                
                    ew = min(e_last, kap_alt * 4)
                    kap_alt = ((kap_alt - ew / 4))
                    
                else:
                    pwm2Bat = 0
                    pwm2PoNet = 0
                    pwm2Dev = 1
                    ew = min(last_alt, kap_alt * 4)
                    kap_alt = ((kap_alt - ew / 4))  

    else:
        if l_preis<=a_preis:
            print("太阳能送电到电网")
            if kap_alt != max_kap:#电池没有充满才进行控制。
                print("太阳能2到电池")
                if abs(last_alt) < l_last:
                    pwm2Bat = 1#太阳能全力给电池充电
                    pwm2PoNet = 0#太阳能给的电满足电池，没有剩余，不给电网供电
                    pwm2Dev = 0 #电池不需要给用电器供电。因为太阳能供电够了 
                    dif_kap = max_kap - kap_alt              
                    ew = min(abs(last_alt, dif_kap * 4.0))                    
                    ew = min(ew, l_last)                 
                    kap_alt = ((kap_alt + (ew / 4)))
                else:
                    pwm2Bat = l_last / abs(last_alt)#太阳能一部分给电池
                    print("太阳能2电网")
                    pwm2PoNet = (abs(last_alt) - l_last) / abs(last_alt)#太阳能另一部分给电网
                    pwm2Dev = 0#电池不需要给用电器供电
                    dif_kap = max_kap - kap_alt
                    ew = min(abs(last_alt), dif_kap * 4.0)
                    ew = min(ew, l_last)
                    kap_alt = ((kap_alt + (ew / 4)))


    print("pwm2Bat: ", pwm2Bat, " pwm2PoNet: ", pwm2PoNet, " pwm2Dev: ", pwm2Dev)

    runCh1(pwm2Bat * 100)
    runCh2(pwm2PoNet * 100)
    runCh3(pwm2Dev * 100)
    # runCh4(pwm2Bat * 100)

    return 





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
