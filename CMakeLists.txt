# SPDX-License-Identifier: AGPL-3.0-only
cmake_minimum_required(VERSION 3.22)
project(AFTERIMAGE VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "")

# JUCE 9.0.5, pinned by commit. Offline: -DFETCHCONTENT_SOURCE_DIR_JUCE=/path/to/JUCE at the same commit.
include(FetchContent)
FetchContent_Declare(JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        d60b7a78030661574a615b586d9325ba7a7fa7dd # 9.0.5
    GIT_PROGRESS   TRUE)
FetchContent_MakeAvailable(JUCE)

juce_add_plugin(AFTERIMAGE
    COMPANY_NAME "Shortwav Labs"
    BUNDLE_ID com.shortwavlabs.afterimage
    PLUGIN_MANUFACTURER_CODE Swlb
    PLUGIN_CODE Aftr
    FORMATS AU VST3 Standalone
    PRODUCT_NAME "AFTERIMAGE"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    COPY_PLUGIN_AFTER_BUILD FALSE)

# Everything the plugin runs, as one interface library: the plugin and each tool compile it into their own binary,
# so the tests exercise exactly the plugin's processor and engine.
add_library(afterimage_shared INTERFACE)
target_sources(afterimage_shared INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/plugin/Source/PluginProcessor.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/plugin/Source/PluginEditor.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/plugin/Source/dsp/Engine.cpp)
target_include_directories(afterimage_shared INTERFACE plugin/Source)
target_compile_definitions(afterimage_shared INTERFACE
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_DISPLAY_SPLASH_SCREEN=0)
target_link_libraries(afterimage_shared INTERFACE
    juce::juce_audio_utils juce::juce_dsp
    juce::juce_recommended_config_flags juce::juce_recommended_lto_flags juce::juce_recommended_warning_flags)

target_link_libraries(AFTERIMAGE PRIVATE afterimage_shared)

foreach(tool afterimage_tests afterimage_render afterimage_bench)
    juce_add_console_app(${tool} PRODUCT_NAME ${tool})
    target_link_libraries(${tool} PRIVATE afterimage_shared)
endforeach()
target_sources(afterimage_tests PRIVATE plugin/tests/Tests.cpp)
target_sources(afterimage_render PRIVATE plugin/tools/Render.cpp)
target_sources(afterimage_bench PRIVATE plugin/tools/Bench.cpp)

enable_testing()
add_test(NAME afterimage_tests COMMAND afterimage_tests)
