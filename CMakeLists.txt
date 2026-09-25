cmake_minimum_required(VERSION 3.18)
project(agentic_trader_core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(AT_BUILD_PYTHON "Build the pybind11 extension module (_atcore)" ON)
option(AT_BUILD_TESTS "Build C++ unit tests" ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_library(at_core STATIC
  cpp/src/indicators.cpp
  cpp/src/backtest.cpp
  cpp/src/risk.cpp
  cpp/src/strategies.cpp)
target_include_directories(at_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/cpp/include)
if(MSVC)
  target_compile_options(at_core PRIVATE /W4 /O2)
else()
  target_compile_options(at_core PRIVATE -Wall -Wextra -O3)
endif()

add_executable(at_backtest cpp/apps/at_backtest.cpp)
target_link_libraries(at_backtest PRIVATE at_core)

if(AT_BUILD_TESTS)
  enable_testing()
  add_executable(at_core_tests cpp/tests/test_core.cpp)
  target_link_libraries(at_core_tests PRIVATE at_core)
  add_test(NAME at_core_tests COMMAND at_core_tests)
endif()

if(AT_BUILD_PYTHON)
  find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
  find_package(pybind11 CONFIG REQUIRED)
  pybind11_add_module(_atcore cpp/bindings/module.cpp)
  target_link_libraries(_atcore PRIVATE at_core)
  # Drop the compiled module straight into the Python package.
  set(_pkg_dir ${CMAKE_CURRENT_SOURCE_DIR}/agentic_trader/quant)
  set_target_properties(_atcore PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${_pkg_dir})
  foreach(cfg IN ITEMS DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
    set_target_properties(_atcore PROPERTIES LIBRARY_OUTPUT_DIRECTORY_${cfg} ${_pkg_dir})
  endforeach()
endif()
