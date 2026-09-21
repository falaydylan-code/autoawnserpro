"""The side panel keeps the controls used for each run on Home."""

from test_extension_coverage import extension


def test_home_has_run_controls_and_settings_has_diagnostics(extension):
    _, worker, _, context, _ = extension
    panel = context.new_page()
    panel.goto(worker.url.rsplit('/', 1)[0] + '/sidepanel.html')
    panel.locator('#model').wait_for(state='visible')

    assert panel.locator('#model').evaluate("e => Boolean(e.closest('#workspace'))")
    assert panel.locator('#advance').is_visible()
    assert panel.locator('#show-cost').is_visible()
    assert panel.locator('#steps').count() == 0
    assert 'No parts planned' not in panel.locator('body').inner_text()
    assert panel.locator('#eth').inner_text() in ('Enable', 'Enabled')
    assert not panel.locator('#copylog').is_visible()

    cost_total = panel.locator('#cost').locator('..')
    assert cost_total.is_visible()
    panel.locator('#show-cost').uncheck()
    assert not cost_total.is_visible()
    panel.locator('#show-cost').check()
    assert cost_total.is_visible()

    panel.locator('#settings-toggle').click()
    assert panel.locator('#copylog').is_visible()
    assert not panel.locator('#model').is_visible()
    panel.locator('#settings-back').click()
    assert panel.locator('#model').is_visible()
    panel.close()
