cmake_minimum_required(VERSION 3.5)
project(catchup_timestamp_tests LANGUAGES CXX)

enable_testing()
find_path(KODI_INCLUDE_DIR kodi/c-api/addon-instance/inputstream/timing_constants.h REQUIRED)
add_executable(test_catchup_timestamps TestCatchupTimestampNormalizer.cpp)
target_include_directories(test_catchup_timestamps PRIVATE "${KODI_INCLUDE_DIR}")
set_target_properties(test_catchup_timestamps PROPERTIES CXX_STANDARD 11 CXX_STANDARD_REQUIRED ON)
add_test(NAME catchup_timestamps COMMAND test_catchup_timestamps)

add_executable(test_tempo_map tempomap_test.cpp)
target_include_directories(test_tempo_map PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../src/stream")
set_target_properties(test_tempo_map PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON)
add_test(NAME tempo_map COMMAND test_tempo_map)
