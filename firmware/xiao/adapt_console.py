"""Small, explicit adaptations of the pinned upstream console example.

Upstream remains in the ignored build workspace. Its license headers are kept.
The official motion computation and decision expressions are not replaced.
"""
from pathlib import Path


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Pinned upstream source did not match the expected patch')
    return text.replace(old, new, 1)


def adapt(project: Path):
    main = project / 'main/app_main.c'
    code = main.read_text(encoding='utf-8')
    code = replace_once(code, '#if CONFIG_IDF_TARGET_ESP32C5 || CONFIG_IDF_TARGET_ESP32C61',
                        '#if CONFIG_IDF_TARGET_ESP32C5 || CONFIG_IDF_TARGET_ESP32C6 || CONFIG_IDF_TARGET_ESP32C61')
    code = replace_once(code, '''        esp_radar_config_t radar_config;
        esp_radar_get_config(&radar_config);
        esp_radar_wifi_reinit(&radar_config.wifi_config);''', '''        // wifi_cmd owns reconnection. Do not recreate the existing STA netif.
        if (g_ping_handle != NULL) {
            esp_ping_stop(g_ping_handle);
        }''')
    code = replace_once(code, '''    esp_console_dev_uart_config_t uart_config = ESP_CONSOLE_DEV_UART_CONFIG_DEFAULT();
    repl_config.prompt = "csi>";
    ESP_ERROR_CHECK(esp_console_new_repl_uart(&uart_config, &repl_config, &repl));''', '''    esp_console_dev_usb_serial_jtag_config_t usb_config = ESP_CONSOLE_DEV_USB_SERIAL_JTAG_CONFIG_DEFAULT();
    repl_config.prompt = "csi>";
    ESP_ERROR_CHECK(esp_console_new_repl_usb_serial_jtag(&usb_config, &repl_config, &repl));''')
    code = replace_once(code, '    esp_radar_dec_config_t dec_config = ESP_RADAR_DEC_CONFIG_DEFAULT();',
                        '''    esp_radar_dec_config_t dec_config = ESP_RADAR_DEC_CONFIG_DEFAULT();
    // Match the official 11n radio profile and the C6 HT-LTF output.
    csi_config.acquire_csi_lltf = false;
    dec_config.ltf_type = RADAR_LTF_TYPE_HTLTF;
    dec_config.sub_carrier_step_size = 5;''')
    code = replace_once(code, 'static int wifi_cmd_radar(int argc, char **argv)',
                        'static bool g_ghost_calibrated = false;\n\nstatic int wifi_cmd_radar(int argc, char **argv)')
    code = replace_once(code, '''        esp_radar_train_start();
        g_console_input_config.train_start = true;''', '''        g_ghost_calibrated = false;
        esp_err_t train_result = esp_radar_train_start();
        g_console_input_config.train_start = (train_result == ESP_OK);
        printf("GHOST_TRAIN,%s,%d\\n", train_result == ESP_OK ? "STARTED" : "ERROR", train_result);
        if (train_result != ESP_OK) return train_result;''')
    code = replace_once(code, '''        esp_radar_train_stop(&g_console_input_config.predict_someone_threshold,
                             &g_console_input_config.predict_move_threshold);
        g_console_input_config.train_start = false;''', '''        esp_err_t train_result = esp_radar_train_stop(&g_console_input_config.predict_someone_threshold,
                             &g_console_input_config.predict_move_threshold);
        g_console_input_config.train_start = false;
        g_ghost_calibrated = (train_result == ESP_OK);
        printf("GHOST_TRAIN,%s,%d\\n", train_result == ESP_OK ? "DONE" : "ERROR", train_result);''')
    code = replace_once(code, 'esp_err_t ws2812_led_init(void)', '''static int ghost_status_cmd(int argc, char **argv)
{
    printf("GHOST_STATUS,1,ghost-radar-1,%u,%d,%d,%d,%.9g,%.9g\\n",
           esp_log_timestamp(), g_wifi_connect_status,
           g_console_input_config.train_start, g_ghost_calibrated,
           g_console_input_config.predict_someone_threshold,
           g_console_input_config.predict_move_threshold);
    return 0;
}

esp_err_t ws2812_led_init(void)''')
    code = replace_once(code, '    cmd_register_radar();', '''    cmd_register_radar();
    const esp_console_cmd_t status_cmd = {
        .command = "ghost_status", .help = "Read GHOST protocol and calibration state",
        .func = ghost_status_cmd,
    };
    ESP_ERROR_CHECK(esp_console_cmd_register(&status_cmd));''')
    main.write_text(code, encoding='utf-8')
    defaults = project / 'sdkconfig.defaults'
    lines = defaults.read_text(encoding='utf-8').splitlines()
    lines = [x for x in lines if not x.startswith(('CONFIG_ESP_CONSOLE_UART',
             'CONFIG_ESPTOOLPY_MONITOR_BAUD', 'CONFIG_ESPTOOLPY_BAUD_',
             'CONFIG_ESP32_DEFAULT_CPU_FREQ', 'CONFIG_ESP32S3_DEFAULT_CPU_FREQ'))]
    defaults.write_text('\n'.join(lines) + '\nCONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y\nCONFIG_ESPTOOLPY_MONITOR_BAUD=115200\n', encoding='utf-8')
    (project/'main/idf_component.yml').write_text('''dependencies:
  idf: "==5.5.4"
  espressif/esp-radar: "==0.3.4"
  espressif/led_strip: "==2.5.5"
  espressif/esp_csi_gain_ctrl: "==0.1.5"
  espressif/esp_radar_motion_dec: "==0.1.1"
  espressif/cmake_utilities: "==0.5.3"
''', encoding='utf-8')
    (project/'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS $ENV{IDF_PATH}/examples/system/console/advanced/components)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(ghost_radar)
''', encoding='utf-8')
