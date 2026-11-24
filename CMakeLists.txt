cmake_minimum_required(VERSION 3.21)
project(ss6_native_reconstruction VERSION 0.1.0 LANGUAGES CXX)

option(SS6_BUILD_GAME "Build the SDL3 game executable (ss6-viewer)" ON)
option(SS6_BUILD_TOOLS "Build the probe, trace and replay command-line tools" ON)
option(SS6_BUILD_TESTS "Build the asset-independent tests and register them with CTest" ON)
option(SS6_WARNINGS_AS_ERRORS "Treat compiler warnings in project code as errors" OFF)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# The EE FPU never fuses a multiply into a following add implicitly; the
# explicit MULA/MADD sequences are modeled by ScalarFloat. Keep host floating
# point (including the libgcc soft-double blends) unfused. This is a
# correctness requirement of the simulation, not a tuning flag.
if(MSVC)
  add_compile_options(/fp:precise)
else()
  add_compile_options(-ffp-contract=off)
endif()

add_library(ss6-warnings INTERFACE)
if(MSVC)
  target_compile_options(ss6-warnings INTERFACE /W4 $<$<BOOL:${SS6_WARNINGS_AS_ERRORS}>:/WX>)
else()
  target_compile_options(ss6-warnings INTERFACE -Wall -Wextra -Wpedantic
    $<$<BOOL:${SS6_WARNINGS_AS_ERRORS}>:-Werror>)
endif()

include(cmake/ss6_sources.cmake)

# ---- Runtime library: all game logic, no window-system dependency ----------
add_library(ss6-runtime STATIC)
add_library(ss6::runtime ALIAS ss6-runtime)
foreach(group IN LISTS SS6_RUNTIME_GROUPS)
  string(TOUPPER ${group} upper)
  target_sources(ss6-runtime PRIVATE ${SS6_${upper}_SOURCES})
  source_group(${group} FILES ${SS6_${upper}_SOURCES})
endforeach()
target_include_directories(ss6-runtime PUBLIC src)
target_compile_features(ss6-runtime PUBLIC cxx_std_20)
target_compile_definitions(ss6-runtime PUBLIC SS6_HAVE_PAUSE_ART=1)
target_link_libraries(ss6-runtime PRIVATE ss6-warnings)

# ---- Game executable ------------------------------------------------------
if(SS6_BUILD_GAME)
  find_package(SDL3 CONFIG REQUIRED)
  add_executable(ss6-viewer src/viewer.cpp)
  target_link_libraries(ss6-viewer PRIVATE SDL3::SDL3 ss6::runtime ss6-warnings)
  install(TARGETS ss6-viewer RUNTIME DESTINATION .)
endif()

# ---- Tools ----------------------------------------------------------------
if(SS6_BUILD_TOOLS)
  foreach(entry IN LISTS SS6_TOOLS)
    string(REPLACE "=" ";" pair ${entry})
    list(GET pair 0 tool)
    list(GET pair 1 stem)
    add_executable(${tool} src/${stem}.cpp)
    target_link_libraries(${tool} PRIVATE ss6::runtime)
    set_target_properties(${tool} PROPERTIES FOLDER tools)
  endforeach()
endif()

# ---- Tests ----------------------------------------------------------------
if(SS6_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests)
endif()
