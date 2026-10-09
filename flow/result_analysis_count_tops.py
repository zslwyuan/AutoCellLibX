import glob
from pathlib import Path
import os


def find_stat(lines, key):
    for line in lines:
        if (line.find(key) >= 0):
            return float(line.split(" ")[0])
    assert(False)
    return 1


def mkdir(path_str):
    if os.path.exists(path_str):
        pass
    else:
        os.mkdir(path_str)


output_path = "./results/"

result_file_names = []
for filename in glob.iglob('./outputs/*/best*', recursive=True):
    result_file_names.append(os.path.abspath(filename))

benchmark2stat = dict()
benchmark_names = []
for result_file_name in result_file_names:
    benchmark_name = result_file_name.split("-")[-1]
    benchmark_output_path = '/'.join(result_file_name.split('/')[:-1])
    benchmark_names.append(benchmark_name)

    result_file = open(result_file_name, 'r')
    lines = result_file.readlines()
    result_file.close()

# | designOverallArea | saveArea | saveRatio | patternCnt | patternSize | patternCoverage | patternName | patternCode |
# | 3208.1854600000415 | 81.92000000000002 | 2.862766147790364 | 32 | 4 | 128 | COMPLEX17 | [NAND2X1,NAND2X1,OR2X1]+c2o0_OAI21X1 |
# | 3208.1854600000415 | 67.584 | 2.3617820719270504 | 66 | 3 | 198 | COMPLEX0 | [NAND2X1,NAND2X1,OR2X1] |
# | 3208.1854600000415 | 58.87999999999997 | 2.0576131687243224 | 23 | 5 | 115 | COMPLEX18 | [NAND2X1,NAND2X1,OR2X1]+c2o0_OAI21X1+c0o0_XNOR2X1 |
# | 3208.1854600000415 | 38.912000000000035 | 1.3598139202004238 | 38 | 2 | 76 | COMPLEX1 | [OAI21X1,NAND2X1] |

    target_path = output_path+benchmark_name
    mkdir(target_path)
    os.system('cp '+result_file_name+" "+target_path +
              "/"+benchmark_name+"_summary.csv")
    for line in lines[1:]:
        if (len(line) < 10):
            continue
        complex_name = line.split("|")[7].replace(' ', '')
        os.system('cp '+benchmark_output_path+"/"+complex_name+".* "+target_path)


# print(benchmark2stat)
# csv_file = open(output_path + 'result.csv', 'w')
# print("benchmark | original_astran_total_area | original_gscl_total_area "
#       "| reduce_area_compared_to_astran_total | reduce_area_compared_to_total "
#       "| astran_reduce_area_percentage | GSCLReduceAreaPercentage |", file=csv_file)
# for key in sorted(benchmark_names):
#     print(key, '|', end='', file=csv_file)
#     for value in benchmark2stat[key]:
#         print(value, '|', end='', file=csv_file)
#     print(end='\n', file=csv_file)
# csv_file.close()

# 1625.0880000000009  <- compared to Astran GDS area
# 1.597760919795159 % <- compared to Astran GDS area
# 3736.4217999999987  <- compared to GSCL GDS area
# 1.441069856374211 % <- compared to GSCL GDS area
# The generated complex cells are (name, cluster_num, cell_num_in_one_cluster):
# ('COMPLEX0', 644, 2)
# ('COMPLEX1', 493, 2)
# ('COMPLEX2', 490, 2)
# ('COMPLEX3', 413, 2)
# ('COMPLEX4', 330, 2)


# bestRecordFileList = glob.glob('bestRecord-*')
# print(bestRecordFileList)
