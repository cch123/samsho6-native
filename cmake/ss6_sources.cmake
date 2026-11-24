# Runtime modules of ss6-runtime, grouped by responsibility.
#
# The files live side by side in src/ because the oracle validators in work/ss6
# compile drivers with `-I src` and name sources as src/<file>.cpp. The groups
# below are the logical layout (they also drive IDE source groups); add a new
# file to the group it belongs to.

# Deterministic arithmetic, RNG, task pools, asset lookup, save data.
set(SS6_CORE_SOURCES
  src/asset_files.cpp
  src/fighter_tables.cpp
  src/game_random.cpp
  src/scalar_float.cpp
  src/soft_double.cpp
  src/system_data.cpp
  src/tagged_tasks.cpp
)

# Character-specific actors and companions.
set(SS6_FIGHTERS_SOURCES
  src/andrew_ammo.cpp
  src/chamcham_pet.cpp
  src/chample.cpp
  src/hanzo_capture.cpp
  src/hanzo_projectile.cpp
  src/hanzo_special.cpp
  src/haohmaru_flask.cpp
  src/haohmaru_special.cpp
  src/karakuri_puppet.cpp
  src/karuta.cpp
  src/kazuki_fire.cpp
  src/konru.cpp
  src/mamahaha.cpp
  src/mina_special.cpp
  src/nakoruru_capture.cpp
  src/nakoruru_eagle_attack.cpp
  src/nakoruru_riding.cpp
  src/nakoruru_strikes.cpp
  src/pakupaku_orbit.cpp
  src/poppy.cpp
  src/rera_wolf.cpp
  src/rimururu_special.cpp
)

# Computer-controlled opponent.
set(SS6_CPU_SOURCES
  src/cpu_decision.cpp
  src/cpu_execution.cpp
  src/cpu_input.cpp
  src/cpu_match_control.cpp
  src/cpu_reactions.cpp
  src/cpu_tactics.cpp
  src/cpu_technique.cpp
  src/cpu_technique_script.cpp
)

# Sound selection, sample bank, mixer, music streams.
set(SS6_AUDIO_SOURCES
  src/audio_routing.cpp
  src/combat_audio.cpp
  src/combat_music.cpp
  src/combat_sound_bank.cpp
  src/sound_selection.cpp
)

# Arena state, strips, items and events.
set(SS6_STAGES_SOURCES
  src/combat_stage.cpp
  src/combat_stage_02.cpp
  src/combat_stage_03.cpp
  src/combat_stage_04.cpp
  src/combat_stage_05.cpp
  src/combat_stage_06.cpp
  src/combat_stage_07.cpp
  src/combat_stage_08.cpp
  src/combat_stage_09.cpp
  src/combat_stage_10.cpp
  src/combat_stage_11.cpp
  src/combat_stage_state.cpp
  src/stage_camera.cpp
  src/stage_event.cpp
  src/stage_item_contact.cpp
  src/stage_item_delivery.cpp
  src/stage_item_notices.cpp
  src/stage_item_schedule.cpp
  src/thrown_stage_item.cpp
)

# Pad sampling, command recognition, permissions, action selection.
set(SS6_INPUT_SOURCES
  src/action_selection.cpp
  src/command_input.cpp
  src/human_input.cpp
  src/input_bindings.cpp
  src/input_features.cpp
  src/input_lifecycle.cpp
  src/input_permissions.cpp
  src/input_routes.cpp
  src/key_config.cpp
  src/special_requests.cpp
)

# ACT/JDG playback, object frames, draw preparation, effects.
set(SS6_ANIMATION_SOURCES
  src/action_runtime.cpp
  src/actor_color.cpp
  src/actor_history.cpp
  src/auxiliary_frame.cpp
  src/auxiliary_objects.cpp
  src/character_draw.cpp
  src/character_tiles.cpp
  src/collision.cpp
  src/effect_runtime.cpp
  src/effect_snapshot.cpp
  src/fighter_depth.cpp
  src/judgment.cpp
  src/motion.cpp
  src/native_scene.cpp
  src/object_frame.cpp
  src/player_object.cpp
)

# Round flow, match progress and the playable match driver.
set(SS6_MATCH_SOURCES
  src/battle_round.cpp
  src/ending_playback.cpp
  src/local_versus.cpp
  src/match_ending.cpp
  src/match_progress.cpp
  src/native_match.cpp
  src/native_match_menus.cpp
  src/native_match_practice.cpp
  src/native_match_survival.cpp
  src/practice_dummy.cpp
  src/round_control.cpp
  src/round_dispatcher.cpp
  src/round_initialization.cpp
  src/round_rules.cpp
  src/scheduled_opening.cpp
)

# Menus, mode screens and their art.
set(SS6_MODES_SOURCES
  src/arcade_art.cpp
  src/arcade_ending.cpp
  src/arcade_map.cpp
  src/arcade_presentation.cpp
  src/arcade_ranking.cpp
  src/arcade_results.cpp
  src/arcade_run.cpp
  src/arcade_session.cpp
  src/arcade_talk.cpp
  src/arcade_tally.cpp
  src/character_select.cpp
  src/character_select_art.cpp
  src/color_edit.cpp
  src/console_attract_ranking.cpp
  src/console_gallery.cpp
  src/console_menu.cpp
  src/console_option.cpp
  src/console_ranking_art.cpp
  src/console_title.cpp
  src/console_title_art.cpp
  src/console_versus_art.cpp
  src/console_versus_menu.cpp
  src/console_versus_session.cpp
  src/edit_art.cpp
  src/edit_widgets.cpp
  src/edited_palettes.cpp
  src/fighter_identity_hud.cpp
  src/gallery_art.cpp
  src/menu_canvas.cpp
  src/menu_widgets.cpp
  src/pause_art.cpp
  src/pause_menu.cpp
  src/practice_art.cpp
  src/practice_mode.cpp
  src/skill_list.cpp
  src/spirits_edit.cpp
  src/survival_run.cpp
  src/versus_draw_art.cpp
  src/versus_faceoff.cpp
  src/versus_result.cpp
  src/versus_result_art.cpp
  src/versus_result_text.cpp
  src/vs_curtain.cpp
)

# Contact resolution, damage, reactions, state machine, moves.
set(SS6_COMBAT_SOURCES
  src/actor_state.cpp
  src/battle_gauges.cpp
  src/combat_decision.cpp
  src/combined_slash.cpp
  src/contact_presentation.cpp
  src/contact_trial.cpp
  src/damage.cpp
  src/dash_motion.cpp
  src/finishing_blow.cpp
  src/ground_state.cpp
  src/ground_throw.cpp
  src/jump_motion.cpp
  src/knockdown.cpp
  src/knockout.cpp
  src/ordinary_rules.cpp
  src/projectile_engine.cpp
  src/pursuit_attack.cpp
  src/rage_gauge.cpp
  src/reaction.cpp
  src/script_engine.cpp
  src/script_fighter.cpp
  src/state_callbacks.cpp
  src/state_entry.cpp
  src/state_transition.cpp
  src/ten_chain.cpp
  src/ten_explosion.cpp
  src/throw_victim.cpp
  src/trial_script.cpp
  src/victim_script.cpp
  src/weapon_deflection.cpp
  src/weapon_handling.cpp
  src/weapon_lock.cpp
  src/weapon_pickup.cpp
)

set(SS6_RUNTIME_GROUPS core fighters cpu audio stages input animation match modes combat)

# Command-line tools that link only the runtime: per-function probes driven by
# the validators in work/ss6, plus the trace and replay utilities.
# Each entry is <target>=<source stem>.
set(SS6_TOOLS
  ss6-action-selection-probe=action_selection_probe
  ss6-action-sequence-probe=action_sequence_probe
  ss6-actor-color-probe=actor_color_probe
  ss6-actor-history-probe=actor_history_probe
  ss6-actor-state-probe=actor_state_probe
  ss6-auxiliary-frame-probe=auxiliary_frame_probe
  ss6-auxiliary-objects-probe=auxiliary_objects_probe
  ss6-battle-gauges-probe=battle_gauges_probe
  ss6-battle-round-probe=battle_round_probe
  ss6-character-draw-probe=character_draw_probe
  ss6-character-tiles-probe=character_tiles_probe
  ss6-collision-probe=collision_probe
  ss6-combat-probe=combat_probe
  ss6-command-input-probe=command_input_probe
  ss6-contact-trial-probe=contact_trial_probe
  ss6-damage-probe=damage_probe
  ss6-effect-probe=effect_probe
  ss6-ending-playback-probe=ending_playback_probe
  ss6-finishing-blow-probe=finishing_blow_probe
  ss6-ground-state-probe=ground_state_probe
  ss6-input-bindings-probe=input_bindings_probe
  ss6-input-features-probe=input_features_probe
  ss6-input-lifecycle-probe=input_lifecycle_probe
  ss6-input-permissions-probe=input_permissions_probe
  ss6-input-stream-probe=input_stream_probe
  ss6-knockdown-probe=knockdown_probe
  ss6-knockout-probe=knockout_probe
  ss6-match-ending-probe=match_ending_probe
  ss6-match-progress-probe=match_progress_probe
  ss6-match-replay=match_replay
  ss6-mechanics-probe=mechanics_probe
  ss6-meter-probe=meter_probe
  ss6-object-pool-probe=object_pool_probe
  ss6-ordinary-probe=ordinary_probe
  ss6-player-object-probe=player_object_probe
  ss6-reaction-control-probe=reaction_control_probe
  ss6-reaction-probe=reaction_probe
  ss6-round-control-probe=round_control_probe
  ss6-round-entry-probe=round_entry_probe
  ss6-round-flow-probe=round_flow_probe
  ss6-round-intro-probe=round_intro_probe
  ss6-round-reset-probe=round_reset_probe
  ss6-round-rules-probe=round_rules_probe
  ss6-runtime-trace=runtime_trace
  ss6-scene-audio-probe=scene_audio_probe
  ss6-scheduled-opening-probe=scheduled_opening_probe
  ss6-sound-selection-probe=sound_selection_probe
  ss6-stage-camera-probe=stage_camera_probe
  ss6-state-callbacks-probe=state_callbacks_probe
  ss6-state-entry-probe=state_entry_probe
  ss6-state-transition-probe=state_transition_probe
  ss6-task-dispatch-probe=task_dispatch_probe
  ss6-weapon-lock-actor-probe=weapon_lock_actor_probe
  ss6-weapon-lock-probe=weapon_lock_probe
  ss6-world-effect-probe=world_effect_probe
)
