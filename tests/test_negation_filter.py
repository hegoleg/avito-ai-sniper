"""
Tests for Negation Filter: mask_negations, DEFAULT_EXCLUDES, check_excludes, and is_reserved_text.
Validates Tier 1 (standard) and Tier 2 (boundary, adversarial bait) specifications.
Compatible with pytest and unittest.
"""

import unittest
from negation_filter import (
    DEFAULT_EXCLUDES,
    mask_negations,
    is_reserved_text,
    check_excludes,
)


class TestLegitimateListingsPass(unittest.TestCase):
    """Tier 1: Legitimate hardware listings containing negation phrases or box inclusions must PASS."""

    def test_ne_bitaya(self):
        text = "Видеокарта не битая, в отличном состоянии"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_artefakty_otsutstvuyut(self):
        text = "Артефакты отсутствуют, любые тесты FurMark"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_bez_artefaktov(self):
        text = "Без артефактов и перегрева, стояла в домашнем ПК"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_komplekt_korobka_i_chek(self):
        text = "В комплекте коробка и чек из магазина"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_rodnaya_korobka(self):
        text = "Родная коробка сохранилась, полный комплект"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_bez_defektov_ne_remontirovalas(self):
        text = "Без дефектов, не ремонтировалась, пломбы на месте"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_bez_otvala(self):
        text = "Без отвала чипа, тесты проходит на ура"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_kopiya_cheka(self):
        text = "Оригинал, гарантия ДНС, копия чека в комплекте"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_elektronnaya_kopiya_cheka(self):
        text = "Электронная копия чека на почте, покупалась полгода назад"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_nikakikh_defektov(self):
        text = "Никаких дефектов и артефактов не обнаружено"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_defektov_net(self):
        text = "Дефектов нет, отвала нет, любые проверки приветствуются"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_ne_replika(self):
        text = "Не реплика, 100% оригинал из официального магазина"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_artefakty_colon_otsutstvuyut(self):
        text = "Артефакты: отсутствуют. Идеальное состояние."
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_artefakty_em_dash_otsutstvuyut(self):
        text = "Артефакты — отсутствуют."
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_artefakty_hyphen_otsutstvuyut(self):
        text = "Артефакты - отсутствуют."
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_artefakty_colon_net(self):
        text = "Артефакты: нет. Тесты проходит."
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_otval_colon_net(self):
        text = "Отвал: нет, температуры низкие."
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_otval_em_dash_otsutstvuet(self):
        text = "Отвал — отсутствует."
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_ne_hyphen_bitaya(self):
        text = "не-битая карта в отличном состоянии"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_compound_otvala_i_defektov_net(self):
        text = "Отвала и дефектов нет."
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_compound_defektov_i_artefaktov_net(self):
        text = "дефектов и артефактов нет"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_kopiya_garantiynogo_talona(self):
        text = "копия гарантийного талона в комплекте"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")

    def test_elektronnaya_kopiya_kassovogo_cheka(self):
        text = "электронная копия кассового чека"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected, f"Falsely rejected: {reason}")


class TestDefectiveListingsFail(unittest.TestCase):
    """Tier 1: Genuine defective listings, box-only offers, and traps must FAIL."""

    def test_bitaya_na_zapchasti(self):
        text = "Видеокарта битая, на запчасти"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_artefakty_v_igrah(self):
        text = "Появились артефакты в играх, греется"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_pustaya_korobka(self):
        text = "Пустая коробка от RTX 3070"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_tolko_korobka(self):
        text = "Только коробка от процессора i7"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_kod_43(self):
        text = "Код 43, требуется реболл чипа"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_tsena_za_odnu_plashku(self):
        text = "Цена указана за одну плашку"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_replika(self):
        text = "Реплика AirPods Pro высокое качество"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_ne_vklyuchaetsya(self):
        text = "Материнская плата не включается, не стартует"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_pod_vosstanovlenie(self):
        text = "Под восстановление мастеру или на запчасти"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_korobka_bez_videokarty(self):
        text = "Коробка без видеокарты, состояние хорошее"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_otval_chipa(self):
        text = "Отвал видеочипа, кулера крутятся картинки нет"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_arenda(self):
        text = "Аренда оборудования для майнинга посуточно"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)


class TestNegationAdversarialCombinations(unittest.TestCase):
    """Tier 2: Combinations of negation with genuine defects, edge cases, and casing."""

    def test_negation_bait_ne_bitaya_no_artefaktit(self):
        """Negated word must not protect an unnegated defect later in the sentence."""
        text = "Карта не битая, но артефактит в тестах"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected, "Failed to reject unnegated defect 'артефактит'")

    def test_negation_bait_bez_korobki_na_zapchasti(self):
        """Legitimate packaging phrase must not protect 'на запчасти'."""
        text = "Продается без коробки, строго на запчасти"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected, "Failed to reject defect 'на запчасти'")

    def test_negation_bait_ne_dlya_igr(self):
        """'Не для игр' should not mask 'под восстановление'."""
        text = "Не для игр, под восстановление или на запчасти"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_adversarial_colon_trap(self):
        """Colon followed by positive defect must still trigger exclude."""
        text = "Артефакты: есть в 3D приложениях"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_adversarial_hyphen_trap(self):
        """'Не-битая' combined with 'отвал чипа' must be rejected."""
        text = "не-битая, но отвал чипа"
        is_rejected, reason = check_excludes(text)
        self.assertTrue(is_rejected)

    def test_uppercase_negations(self):
        text = "ВИДЕОКАРТА НЕ БИТАЯ, БЕЗ ДЕФЕКТОВ, РОДНАЯ КОРОБКА"
        is_rejected, reason = check_excludes(text)
        self.assertFalse(is_rejected)

    def test_custom_user_excludes_word_boundaries(self):
        """Custom exclude word 'бан' should not trigger on 'банка'."""
        text = "Оригинальная упаковка, железная банка"
        is_rejected, reason = check_excludes(text, custom_excludes=["бан"])
        self.assertFalse(is_rejected)

        text_trigger = "Получен бан по железу"
        is_rejected, reason = check_excludes(text_trigger, custom_excludes=["бан"])
        self.assertTrue(is_rejected)

    def test_empty_and_none_text(self):
        self.assertEqual(mask_negations(""), "")
        self.assertEqual(mask_negations(None), "")
        self.assertFalse(check_excludes("")[0])
        self.assertFalse(check_excludes(None)[0])


class TestIsReservedTextScenarios(unittest.TestCase):
    """Tier 1 & 2: Verification of reservation indicators respecting negations."""

    def test_reserved_positive_cases(self):
        self.assertTrue(is_reserved_text("Товар зарезервирован покупателем"))
        self.assertTrue(is_reserved_text("В резерве до 18:00"))
        self.assertTrue(is_reserved_text("Заказ оформлен через Авито Доставку"))
        self.assertTrue(is_reserved_text("Бронь за Алексеем"))
        self.assertTrue(is_reserved_text("Товар продан, объявление закрыто"))

    def test_reserved_negation_cases(self):
        self.assertFalse(is_reserved_text("Без брони и резерва, кто первый приехал тот забрал"))
        self.assertFalse(is_reserved_text("Не в резерве, объявление актуально"))
        self.assertFalse(is_reserved_text("Бронь не ставлю, торга нет"))
        self.assertFalse(is_reserved_text("Брони нет, только прямая продажа"))
        self.assertFalse(is_reserved_text("Пока объявление висит товар не продан"))

    def test_reserved_empty_and_none(self):
        self.assertFalse(is_reserved_text(""))
        self.assertFalse(is_reserved_text(None))


if __name__ == "__main__":
    unittest.main()
