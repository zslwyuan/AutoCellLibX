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

    astran_reduce_area = find_stat(lines, "compared to Astran GDS area")
    astran_reduce_area_percentage = find_stat(
        lines, "% <- compared to Astran GDS area")
    GSCLReduceArea = find_stat(lines, "compared to GSCL GDS area")
    GSCLReduceAreaPercentage = find_stat(
        lines, "% <- compared to GSCL GDS area")

    benchmark2stat[benchmark_name] = [
        astran_reduce_area/astran_reduce_area_percentage *
        100, GSCLReduceArea/GSCLReduceAreaPercentage*100,
        astran_reduce_area, GSCLReduceArea,
        astran_reduce_area_percentage, GSCLReduceAreaPercentage]

    target_path = output_path+benchmark_name
    mkdir(target_path)
    os.system('cp '+result_file_name+" "+target_path)
    for line in lines[5:]:
        complex_name = line.split("\'")[1]
        os.system('cp '+benchmark_output_path+"/"+complex_name+".* "+target_path)


print(benchmark2stat)
csv_file = open(output_path + 'result.csv', 'w')
print("benchmark | original_astran_total_area | original_gscl_total_area "
      "| reduce_area_compared_to_astran_total | reduce_area_compared_to_total "
      "| astran_reduce_area_percentage | GSCLReduceAreaPercentage |", file=csv_file)
for key in sorted(benchmark_names):
    print(key, '|', end='', file=csv_file)
    for value in benchmark2stat[key]:
        print(value, '|', end='', file=csv_file)
    print(end='\n', file=csv_file)
csv_file.close()

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
