#!/usr/bin/env python3
"""Install the built viewer with a fresh inode for macOS executable caching."""
from fighter_roster import PLAYABLE, SELECTABLE, GRID
import os,shutil,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for resource in ['input_commands.bin','input_normal.bin','input_special.bin','input_characters.bin','input_categories.bin',
                 'selection_normal.bin','selection_attack.bin','selection_chain.bin','selection_normal_map.bin','selection_attack_map.bin','selection_normal_descriptors.bin',
                 'selection_character_flags.bin','selection_threat_actions.bin',
                 'permission_air_rectangles.bin','permission_target_ranges.bin','permission_attack_ranges.bin','permission_systems.bin','permission_limits.bin','permission_gate_limits.bin','permission_cancel_conditions.bin',
                 'entry_attack.bin','entry_special.bin','entry_damage.bin','entry_conditions.bin','entry_special_exceptions.bin',
                 'callback_attack_handlers.bin','callback_special_parameters.bin','callback_character_parameters.bin','callback_constants.bin',
                 'weapon_positions.bin','script_rows.bin','action_locks.bin','projectile_descriptors.bin','victim_rows.bin','depth_rules.bin','victim_facing_pairs.bin','victim_hold_pairs.bin','fighter_stubs.bin','form_actions.bin','angle_trig.bin','weapon_constants.bin','weapon_lock.bin','aid_51.bin','act_51.bin','jdg_51.bin','pil_51.bin','idx_51.bin','map_51.bin','chr_51.bin','sound_selection.bin','combat_sound_bank.bin','bgm01_l.vb','bgm01_r.vb','bgm02_l.vb','bgm02_r.vb','bgm05_l.vb','bgm05_r.vb','bgm06_l.vb','bgm06_r.vb','bgm24_l.vb','bgm24_r.vb','stage_event.bin','stage_item_schedule.bin','opening_tasks.bin','ending_tasks.bin','ending_choices.bin',
                 'contact_effects.bin','effect03.tex','effect04.tex','effect05.tex','effect09.tex','04tenso.bin','effect06.tex','effect07.tex','effect08.tex','world_effects.bin','effect_descriptors.bin','02Guard.bin','03etc.bin','effect02.tex','01HitFlash.bin','Display.bin','Display2.bin','Display3.bin','effect_pal_data.bin',
                 'obj1_16.tex','obj2_16.tex','effect01.tex','moji1.tex','moji2.tex','moji3.tex','moji_e.tex','hanabi1.tex','hanabi2.tex',
                 'ougi1.tex','ougi2.tex','sakura.tex','versus_quotes_00.bin','versus_result_layout.bin',
                 'menu_bg00_00.tex','win_00.tex','win_00.pal','font_otherscene16.tex','obj0.pal',
                 'console_ranking_art.bin','cpu_air_attack_timing.bin','cpu_guard_heights.bin','projectile_descriptor_flags.bin','projectile_hitstop.bin','cpu_technique_slots.bin','cpu_technique_steps.bin','cpu_technique_definitions.bin','cpu_attack_situations.bin','cpu_matchup_ranges.bin','sqDataCm.bin',*[f'sqData{i:02X}.bin' for i in range(51)],
                 'bg_title00.tex','bg_title00.pal','obj0_16.tex','font_coin.tex','vs_curtain.bin','change_base16.tex',*[f'collision_{c:02}.bin' for c in PLAYABLE if c],'vs_faceoff_layout.bin','vs_back.tex','vs_back.pal','vs_obj.tex','vs_obj.pal','character_select_art.bin','spirit_select_art.bin',
                 'ps2_gage_1_2_3_all.tex','ps2_gage_1_2_3_all.pal','ps2_common_icon.tex','ps2_common_icon.pal',
                 'char_face_1024.tex','char_face_1024.pal',
                 *[f'{stem}_{id:02}.bin' for id in (c for c in SELECTABLE if c) for stem in ('aid','act','jdg','pil','idx','map','chr')],
                 *[f'bup_{i:02}.{ext}' for i in sorted({*GRID,48}-{53}) for ext in ('tex','pal')],
                 *[f'vs_voice_{i:02}.bin' for i in (*range(1,43),*range(44,49))],
                 *[f'vs_sounds_{i:02}.bin' for i in (*(c for c in SELECTABLE if c),51,52)],
                 *[f'bg{arena:02}_{page}.{ext}' for arena in (0,1) for ext,pages in (('tex',(1,2,3,4)),('pal',(1,3))) for page in pages],
                 'save_default.bin','console_option.bin','spirits_edit.bin','edit_widgets.bin','arcade_tally.bin','arcade_run.bin','arcade_map.bin','practice_art.bin','arcade_art.bin','pause_menu.bin','practice_mode.bin','skill_list.bin','menu_canvas.bin','PS2_menu_bg00_00.tex','PS2_menu_bg00_00.pal','character_select_mode_art.bin','menu_widgets.bin','console_gallery.bin','survival_run.bin','color_edit.bin','console_versus_art.bin','combat_stage.bin','combat_stage_01.bin',
                 # Menu scenes: edit and gallery art tables, the 55 gallery pictures and the arena
                 # streams the sound test can request. pause_art.bin exists once its extractor has run.
                 'edit_art.bin','gallery_art.bin',*(['pause_art.bin'] if (ROOT/'work/ss6/extracted/resources/pause_art.bin').exists() else []),
                 *[f'gl_{i:02}.{ext}' for i in range(55) for ext in ('tex','pal')],
                 *[f'bgm{i:02}_{side}.vb' for i in range(7,15) for side in 'lr'],
                 # ARCADE presentation scenes (docs/mode-arcade-map/talk/results/ending/ranking.txt):
                 # tables, map / balloon / caption sheets, demo portraits, win portraits, ending
                 # pictures, the ending object resource 99a and the ranking sheets.
                 'arcade_talk.bin','arcade_results.bin','arcade_ending.bin','arcade_ranking.bin',
                 'map_main.tex','map_main.pal','map_cloud.tex','moji4.tex','moji5.tex','hukidasi.tex','hukidasi2.tex',
                 'demo_mga.tex','demo_mga.pal','menu_bg01_00.tex','menu_bg01_00.pal','font_otherscene2_16.tex',
                 'rank_obj.tex','cloud_l.tex','cloud_r.tex','face.tex',
                 *[f'{stem}_99a.bin' for stem in ('aid','act','jdg','pil','idx','map','chr')],
                 *sorted(p.name for pattern in ('map_icon_*.tex','map_icon_*.pal','demo_[0-9]*.tex','demo_[0-9]*.pal',
                                                'win_*.tex','win_*.pal','ed_bg*.tex','ed_bg*.pal')
                         for p in (ROOT/'work/ss6/extracted/resources').glob(pattern))]:
 shutil.copy2(ROOT/'work/ss6/extracted/resources'/resource,ROOT/'outputs/ss6-feasibility/native-viewer/assets'/resource)
target=ROOT/'outputs/ss6-feasibility/native-viewer/ss6-viewer'
shutil.copy2(ROOT/'README.txt',target.parent/'README.txt')
fd,name=tempfile.mkstemp(prefix='ss6-viewer.',dir=target.parent);os.close(fd)
try:
 # In-place overwrite produced SIGKILL on this host despite codesign --verify
 # succeeding. Atomic replacement preserves a fresh signed executable inode.
 # SS6_VIEWER_BUILD selects another build directory (default build-native).
 shutil.copy2(ROOT/'work/ss6'/os.environ.get('SS6_VIEWER_BUILD','build-native')/'ss6-viewer',name)
 os.replace(name,target)
finally:
 Path(name).unlink(missing_ok=True)
print(target)
