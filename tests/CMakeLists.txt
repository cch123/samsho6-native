# Tests here must not need the disc image or extracted game data, so they run
# on any checkout. Comparisons against the original executable stay in
# work/ss6/validate_*.py.
add_executable(ss6-test-asset-files test_asset_files.cpp)
target_link_libraries(ss6-test-asset-files PRIVATE ss6::runtime ss6-warnings)
add_test(NAME asset_files COMMAND ss6-test-asset-files)

find_package(Python3 COMPONENTS Interpreter)
if(Python3_FOUND)
  add_test(NAME texture_codec
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_ss6tex.py)
  add_test(NAME sprite_codec
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_ss6sprite.py)
endif()
