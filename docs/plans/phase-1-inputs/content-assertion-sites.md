# Phase 1 input: assertion sites whose expected content may change

Generated during planning, from the tree at Phase 0's final commit. This is
the raw enumeration the spec requires; Task 2 classifies each site.

## How to classify

For each site, ask: **does the assertion compare against text this codebase
generates for a human to read?**

- **A (symmetric-safe)** — the asserted value is a fixture slug, a filename
  derived from one, a placeholder token, a JSON key, or a literal the test
  itself supplies as input. Renaming both sides preserves what the test
  proves. No re-derivation needed.
- **B (must re-derive)** — the asserted value is output this code produces:
  cleaned caption text, an error message's wording, a readable report's
  prose, a hashtag string, a thumbnail line. Translating both sides keeps the
  test green while changing what it proves. For each B site the plan must
  record what the test proves and how the new expectation was obtained --
  by running the new code, not by translating the old string.

## Known gap in this enumeration

This list was produced by a **line-based** scan: it matched an assertion only
when the accented text or a Portuguese keyword appeared on the same physical
line as the `assert`. Two consequences, both found after the fact:

- A multi-line assertion whose content sits on a continuation line was missed.
  `tests/test_render.py:251` — `assertEqual(linhas, [...five-line split...])` —
  is the clearest case, and it is the single most width-sensitive assertion in
  the codebase.
- The Portuguese-keyword list was hand-written, so any word not on it was
  invisible. `linhas` was not on it, which hid every `r["linhas"]` assertion in
  `test_post_instagram.py`.

A re-extraction that joins logical statements by paren balance, and that
matches every `old` name from the rename map rather than a hand-written list,
found 13 width-dependent sites absent from the original 94. They were added in
Task 2's fix round 1.

The lesson is Phase 0's, recurring: the scan was thorough about the shape of
assertion it was written for. If you extend this artifact, join statements
before matching, and derive the word list from the rename map rather than from
memory.

A site can be B even when it looks trivial. `assertIn("legenda", msg)` is B:
it pins a word in a user-facing error message, and the English message must
be checked to genuinely contain the chosen word, not assumed to.


Total assertion sites: 94

Distinct tests: 74

## `tests/test_brief.py::test_metadados_formatados`  (1 site)
  - L36: `self.assertIn("Ribeirão Açaí", m)`

## `tests/test_brief.py::test_substitui_placeholder_de_metadados`  (1 site)
  - L49: `self.assertNotIn("{{METADADOS}}", out)`

## `tests/test_brief.py::test_estado_legivel_primeira_rodada`  (1 site)
  - L64: `self.assertIn("PRIMEIRA RODADA", txt)`

## `tests/test_brief.py::test_traz_a_fala_dentro_do_corte`  (2 sites)
  - L104: `self.assertIn("corte1_mar_azul", texto)`
  - L106: `self.assertIn("E a gente não viu.", texto)`

## `tests/test_brief.py::test_traz_a_fala_do_segmento_que_atravessa_a_fronteira`  (1 site)
  - L123: `self.assertNotIn("não viu", texto)`

## `tests/test_calendario.py::test_slug_de_corte_inexistente_aborta`  (1 site)
  - L50: `self.assertIn("corte99", str(ctx.exception))`

## `tests/test_caption.py::test_junta_descricao_e_hashtags`  (1 site)
  - L14: `self.assertEqual(t, "A frase do corte.\n\n#Um #Dois")`

## `tests/test_caption.py::test_troca_extensao_da_peca`  (1 site)
  - L43: `self.assertEqual(out, os.path.join(self.d, "corte1_short.txt"))`

## `tests/test_caption.py::test_conteudo_gravado_em_utf8`  (1 site)
  - L50: `self.assertEqual(f.read(), "Ação e coração.\n\n#RibeiraoAcai")`

## `tests/test_caption.py::test_sobrescreve_sem_duplicar`  (1 site)
  - L60: `self.assertEqual(txts, ["corte1_short.txt"])`

## `tests/test_caption.py::test_numero_e_rejeitado_citando_o_campo_e_a_peca`  (2 sites)
  - L88: `self.assertIn("corte1", msg)`
  - L89: `self.assertIn("legenda", msg)`

## `tests/test_caption.py::test_avisa_quando_tem_travessao`  (2 sites)
  - L113: `self.assertIn("travessão", saida)`
  - L114: `self.assertIn("corte1", saida)`

## `tests/test_caption.py::test_nao_avisa_sem_travessao`  (1 site)
  - L117: `self.assertEqual(self._valida("Ele avisou. E errou assim mesmo."), "")`

## `tests/test_caption.py::test_titulo_descricao_e_hashtags`  (1 site)
  - L135: `self.assertEqual(t, "O Título\n\nA descrição.\n\n#Um")`

## `tests/test_caption.py::test_sem_titulo_nao_deixa_linha_solta`  (1 site)
  - L138: `self.assertEqual(caption.monta_episodio("", "A descrição.", "#Um"),`

## `tests/test_caption.py::test_so_titulo`  (1 site)
  - L142: `self.assertEqual(caption.monta_episodio("O Título", "", ""), "O Título")`

## `tests/test_curadoria.py::test_novo_estado_tem_meta`  (4 sites)
  - L57: `self.assertEqual(e["meta"], 5)`
  - L58: `self.assertEqual(e["aprovados"], [])`
  - L59: `self.assertEqual(e["rejeitados"], [])`
  - L60: `self.assertEqual(e["rodadas"], 0)`

## `tests/test_curadoria.py::test_duracao_curta_demais`  (1 site)
  - L78: `self.assertTrue(any("duração" in m for m in msgs))`

## `tests/test_curadoria.py::test_duracao_longa_demais`  (1 site)
  - L83: `self.assertTrue(any("duração" in m for m in msgs))`

## `tests/test_curadoria.py::test_recusa_corte_sobreposto`  (1 site)
  - L182: `self.assertIn("sobrepõe", str(cm.exception))`

## `tests/test_curadoria.py::test_aceita_corte_disjunto`  (1 site)
  - L186: `self.assertEqual(len(self.estado["aprovados"]), 2)`

## `tests/test_curadoria.py::test_ajuste_de_tempo_pode_encostar_em_outro`  (2 sites)
  - L196: `self.assertEqual(len(self.estado["aprovados"]), 2)`
  - L197: `self.assertEqual(self.estado["aprovados"][1]["start"], 205.0)`

## `tests/test_curadoria.py::test_mesmo_slug_e_ajuste_de_tempo`  (2 sites)
  - L208: `self.assertEqual(len(self.estado["aprovados"]), 1)`
  - L209: `self.assertEqual(self.estado["aprovados"][0]["start"], 105.0)`

## `tests/test_curadoria.py::test_suprime_alertas_que_leem_speaker`  (1 site)
  - L238: `self.assertFalse(any("convidado fala só" in a for a in alertas), alertas)`

## `tests/test_curadoria.py::test_detecta_se_nao_me_engano`  (1 site)
  - L278: `self.assertTrue(curadoria.tem_hesitacao_numerica("se eu não me engano, 12"))`

## `tests/test_curadoria.py::test_texto_sem_numero_nao_alerta`  (1 site)
  - L284: `self.assertFalse(curadoria.tem_hesitacao_numerica("acho que é importante"))`

## `tests/test_curadoria.py::test_aprovar_adiciona`  (1 site)
  - L383: `self.assertEqual(len(self.estado["aprovados"]), 1)`

## `tests/test_curadoria.py::test_rejeitar_registra_motivo`  (1 site)
  - L388: `self.assertEqual(self.estado["rejeitados"][0]["motivo"], "gancho fraco")`

## `tests/test_curadoria.py::test_tipos_ausentes`  (1 site)
  - L409: `self.assertIn("tese", faltando)`

## `tests/test_curadoria.py::test_motivos_acumulados`  (1 site)
  - L415: `self.assertEqual(curadoria.motivos(self.estado), ["muito técnico"])`

## `tests/test_curadoria.py::test_exporta_momentos_com_campos_do_render`  (1 site)
  - L435: `self.assertEqual(m["slug"], "corte1")`

## `tests/test_encerramento.py::test_nao_deixa_temporario_para_tras`  (1 site)
  - L94: `self.assertEqual(sobras, [], f"temporário ficou para trás: {sobras}")`

## `tests/test_episodio.py::test_campo_faltando_da_erro_claro`  (1 site)
  - L49: `self.assertNotIn("temporada", msg)   # presente, não deve ser listado`

## `tests/test_episodio.py::test_save_load_roundtrip_preserva_acento`  (1 site)
  - L74: `self.assertIn("Ribeirão Açaí", f.read())`

## `tests/test_hashtags.py::test_remove_acento_e_espaco`  (1 site)
  - L9: `self.assertEqual(hashtags.slug("São Bento"), "SaoBento")`

## `tests/test_hashtags.py::test_ribeirao_acai`  (1 site)
  - L12: `self.assertEqual(hashtags.slug("Ribeirão Açaí"), "RibeiraoAcai")`

## `tests/test_hashtags.py::test_planicie_valley`  (1 site)
  - L15: `self.assertEqual(hashtags.slug("Planície Valley"), "PlanicieValley")`

## `tests/test_integracao.py::test_fluxo_curadoria_ate_momentos`  (1 site)
  - L60: `self.assertEqual(momentos[0]["slug"], "corte1")`

## `tests/test_layout.py::test_briefs_por_tipo`  (1 site)
  - L28: `self.assertTrue(layout.brief(self.d, "cortes").endswith("briefs/cortes.md"))`

## `tests/test_layout.py::test_move_tudo_para_o_lugar_certo`  (1 site)
  - L66: `self.assertTrue(os.path.exists(layout.brief(d, "cortes")))`

## `tests/test_layout.py::test_e_idempotente`  (1 site)
  - L98: `self.assertEqual(layout.migrar(d), [])   # 2ª vez não move nada`

## `tests/test_layout.py::test_duplicata_nao_e_apagada_em_silencio`  (1 site)
  - L144: `self.assertTrue(os.path.exists(bak))            # o antigo não sumiu`

## `tests/test_layout.py::test_pasta_de_saida_duplicada_e_reportada`  (1 site)
  - L210: `self.assertTrue(movidos, "mover conteúdo órfão precisa aparecer no relatório")`

## `tests/test_post_instagram.py::test_citacao_longa_e_rejeitada_com_o_excesso`  (1 site)
  - L47: `self.assertIn("linha", r["motivo"])`

## `tests/test_post_instagram.py::test_palavra_mais_larga_que_o_card_e_rejeitada`  (1 site)
  - L62: `self.assertIn("não cabe na largura", r["motivo"])`

## `tests/test_post_instagram.py::test_autor_vem_do_episodio_json`  (1 site)
  - L128: `self.assertEqual(a["cargo"], "Sócio")`

## `tests/test_post_instagram.py::test_contracoes_sao_expandidas`  (2 sites)
  - L174: `self.assertIn("está", t)`
  - L175: `self.assertNotIn(" tá ", f" {t} ")`

## `tests/test_post_instagram.py::test_card_unico_tem_txt_com_o_slug`  (1 site)
  - L273: `self.assertEqual(f.read(), "A legenda do post.\n\n#Um #Dois")`

## `tests/test_post_instagram.py::test_sem_legenda_avisa_e_grava_hashtags`  (2 sites)
  - L290: `self.assertIn("corte3", buf.getvalue())`
  - L291: `self.assertIn("sem legenda", buf.getvalue())`

## `tests/test_post_instagram.py::test_legenda_nao_texto_e_rejeitada`  (1 site)
  - L306: `self.assertIn("corte1", str(e.exception))`

## `tests/test_publicado.py::test_grava_na_hora_e_rele`  (2 sites)
  - L38: `self.assertEqual(r["slug"], "corte1")`
  - L40: `self.assertIn("publicado_em", r)`

## `tests/test_publicado.py::test_encontra_por_plataforma_e_slug`  (4 sites)
  - L60: `self.assertTrue(publicado.ja_publicado(reg, "youtube_shorts", "corte1"))`
  - L63: `self.assertFalse(publicado.ja_publicado(reg, "instagram_reels", "corte1"))`
  - L64: `self.assertFalse(publicado.ja_publicado(reg, "youtube_shorts", "corte2"))`
  - L65: `self.assertFalse(publicado.ja_publicado({}, "youtube_shorts", "corte1"))`

## `tests/test_publish.py::test_publica_tudo_e_registra_cada_um`  (3 sites)
  - L159: `self.assertTrue(publicado.ja_publicado(reg, "youtube_shorts", "corte1"))`
  - L160: `self.assertTrue(publicado.ja_publicado(reg, "instagram_reels", "corte1"))`
  - L165: `self.assertIn("Legenda do corte.", args[2])`

## `tests/test_publish.py::test_falha_numa_plataforma_nao_trava_as_outras`  (1 site)
  - L179: `self.assertFalse(publicado.ja_publicado(reg, "youtube_shorts", "corte1"))`

## `tests/test_publish.py::test_registro_que_falha_depois_do_ar_nao_vira_retentativa`  (2 sites)
  - L215: `self.assertTrue(yt_r["ok"])           # está no ar: não é falha`
  - L218: `self.assertIn("disco cheio", yt_r["erro"])`

## `tests/test_publish_instagram.py::test_status_error_vira_falha_com_o_status_na_mensagem`  (1 site)
  - L88: `self.assertIn("ERROR", str(ctx.exception))`

## `tests/test_publish_instagram.py::test_imagem_com_container_em_erro_nao_publica`  (2 sites)
  - L177: `self.assertIn("ERROR", str(ctx.exception))`
  - L178: `self.assertEqual(req.post.call_count, 1)  # não chamou media_publish`

## `tests/test_render.py::test_segmento_fora_do_corte_nao_entra`  (1 site)
  - L138: `self.assertNotIn("Depois do corte", " ".join(t for _, _, t in itens))`

## `tests/test_render.py::test_sem_legenda_post_avisa_e_grava_hashtags`  (1 site)
  - L333: `self.assertIn("sem legenda_post", buf.getvalue())`

## `tests/test_render.py::test_grava_titulo_descricao_e_hashtags`  (1 site)
  - L425: `self.assertEqual(f.read(), "O Título\n\nA descrição.\n\n#Um")`

## `tests/test_textos.py::test_thumb_args_a_partir_do_episodio`  (1 site)
  - L25: `self.assertIn("Ribeirão Açaí", args["subtitulo"])`

## `tests/test_textos.py::test_selo_tem_codigo_do_episodio`  (1 site)
  - L36: `self.assertIn("T2E07", args["selo"])`

## `tests/test_txt_parse.py::test_remove_marcacao_de_som_e_entidades`  (1 site)
  - L61: `self.assertNotIn("[música]", todo)`

## `tests/test_utils.py::test_remove_marcacao_minuscula`  (1 site)
  - L9: `self.assertEqual(utils.strip_markup("[música] olá"), "olá")`

## `tests/test_utils.py::test_remove_marcacao_maiuscula`  (1 site)
  - L13: `self.assertEqual(utils.strip_markup("[MÚSICA] olá"), "olá")`

## `tests/test_utils.py::test_remove_capitalizada`  (1 site)
  - L16: `self.assertEqual(utils.strip_markup("[Risadas] olá"), "olá")`

## `tests/test_utils.py::test_remove_palmas`  (1 site)
  - L19: `self.assertEqual(utils.strip_markup("[Palmas] olá"), "olá")`

## `tests/test_utils.py::test_remove_variantes_singular_plural`  (1 site)
  - L23: `self.assertEqual(utils.strip_markup(f"{tag} olá"), "olá", msg=tag)`

## `tests/test_utils.py::test_colapsa_espaco_deixado_pela_remocao`  (1 site)
  - L36: `self.assertNotIn("  ", utils.strip_markup("olá [música] mundo"))`

## `tests/test_utils.py::test_expande_contracoes`  (2 sites)
  - L111: `self.assertEqual(utils.clean_caption("tá do seu lado"), "está do seu lado")`
  - L113: `self.assertEqual(utils.clean_caption("eu tô vendo"), "eu estou vendo")`

## `tests/test_utils.py::test_nao_expande_pro_em_locucao`  (1 site)
  - L118: `self.assertEqual(utils.clean_caption("o pro labore dos sócios"),`

## `tests/test_utils.py::test_contracao_respeita_fronteira_de_palavra`  (1 site)
  - L133: `self.assertEqual(utils.clean_caption("está montado"), "está montado")`

## `tests/test_utils.py::test_remove_ne_interrogativo`  (2 sites)
  - L139: `self.assertEqual(utils.clean_caption("é isso, né?"), "é isso.")`
  - L140: `self.assertEqual(utils.clean_caption("olha, né, eu acho"), "olha, eu acho")`

## `tests/test_utils.py::test_preserva_maiuscula_inicial`  (1 site)
  - L143: `self.assertEqual(utils.clean_caption("Tá bom"), "Está bom")`

