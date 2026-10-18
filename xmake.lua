set_project("nohit-native")
set_version("0.1.0")
set_xmakever("2.9.0")
set_languages("c++17")
add_rules("mode.release", "mode.debug")

option("highway")
    set_default(true)
    set_showmenu(true)
    set_description("Use Highway SIMD from the vcpkg manifest installation")
option_end()
option("pdqsort")
    set_default(true)
    set_showmenu(true)
    set_description("Use vcpkg pdqsort for totally ordered beam rankings")
option_end()
option("host_tune")
    set_default(false)
    set_showmenu(true)
    set_description("Compile for this CPU; disable for distribution")
option_end()
option("vcpkg_triplet")
    set_default(is_host("windows") and "x64-windows-static" or is_host("macosx") and "arm64-osx" or "x64-linux")
    set_showmenu(true)
option_end()
option("vcpkg_installed")
    set_default("vcpkg_installed")
    set_showmenu(true)
    set_description("Manifest installation root created by vcpkg install")
option_end()

target("native_frontier")
    set_kind("shared")
    set_basename("_native_frontier")
    set_prefixname("")
    add_files("nohit/engine/native_frontier.cpp")
    add_headerfiles("nohit/engine/native_simd.hpp")
    if is_plat("windows") then
        set_runtimes("MT")
        add_cxxflags("/O2", "/fp:strict", {force = true})
        add_rules("utils.symbols.export_all")
    else
        add_cxxflags("-O3", "-ffp-contract=off", "-fno-fast-math", "-pthread", {force = true})
        add_syslinks("pthread")
        if has_config("host_tune") then
            add_cxxflags("-march=native", "-mtune=native", {force = true})
        end
    end
    if has_config("highway") or has_config("pdqsort") then
        local prefix = path.join(get_config("vcpkg_installed"), get_config("vcpkg_triplet"))
        add_includedirs(path.join(prefix, "include"))
    end
    if has_config("pdqsort") then
        add_defines("NOHIT_WITH_PDQ=1")
    end
    if has_config("highway") then
        local prefix = path.join(get_config("vcpkg_installed"), get_config("vcpkg_triplet"))
        add_defines("NOHIT_WITH_HIGHWAY=1", "HWY_COMPILE_ONLY_STATIC=1")
        -- This kernel uses Highway's header-only static target. vcpkg remains
        -- the sole dependency resolver; no xmake-repo or system copy is used.
        before_build(function (target)
            assert(os.isfile(path.join(prefix, "include", "hwy", "highway.h")),
                   "Highway missing: run vcpkg install --triplet " .. get_config("vcpkg_triplet"))
        end)
    end
target_end()
