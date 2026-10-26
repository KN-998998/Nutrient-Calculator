from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_dried_red_dates_fill_only_missing_fields_from_product_references():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find(name="紅棗")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (281, 4.72, 0.5, 0.1, 0, 66.52, 63, 5)
    assert not set(profile.missing_nutrients).intersection({
        "saturated_fat_g", "trans_fat_g", "sugars_g"
    })
    assert "calmarketing.com.au/product/dried-red-dates" in profile.source_url
    assert "dried-red-date-4634071" in profile.source_url
    assert "待營養師" in repository.correction_notes[normalize_name("紅棗")]
    result = calculate_recipe(Recipe("紅棗小菜", (IngredientAmount("紅棗", 10),)), repository)
    assert result.status == "review"
    assert result.nutrients_per_serving["sugars_g"] == pytest.approx(6.3)


def test_shrimp_ball_missing_trans_fat_uses_two_fried_shrimp_references():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    for name in ("蝦棗", "蝦棗3個"):
        profile = repository.find(name=name)
        assert profile is not None
        assert (
            profile.energy_kcal,
            profile.protein_g,
            profile.total_fat_g,
            profile.saturated_fat_g,
            profile.trans_fat_g,
            profile.available_carbohydrate_g,
            profile.sugars_g,
            profile.sodium_mg,
        ) == (218, 12.26, 12.94, 1.861, 0.045, 12.41, 0.2, 434)
        assert "172037" in profile.source_url
        assert "fried-shrimp-balls" in profile.source_url
        assert "待營養師" in repository.correction_notes[normalize_name("蝦棗3個")]
        result = calculate_recipe(Recipe("蝦棗小菜", (IngredientAmount(name, 75),)), repository)
        assert result.status == "review"
        assert result.nutrients_per_serving["trans_fat_g"] == pytest.approx(0.03375)


def test_honey_cocktail_sausage_never_uses_honey_nutrients():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name in ("蜜糖雞尾腸", "蜜糖雞尾腸3個"):
        profile = repository.find(name=name)
        assert profile is not None
        assert (
            profile.energy_kcal,
            profile.protein_g,
            profile.total_fat_g,
            profile.saturated_fat_g,
            profile.trans_fat_g,
            profile.available_carbohydrate_g,
            profile.sugars_g,
            profile.sodium_mg,
        ) == (250, 16, 18, 6, 0.1, 5, 3, 660)
        assert profile.source_type == "reference_other"
        assert "honey-garlic-pork-sausages-4893475" in profile.source_url
        assert "非採購品" in repository.correction_notes[normalize_name(name)]
        result = calculate_recipe(
            Recipe("雞尾腸小菜", (IngredientAmount(name, 56.7),)), repository
        )
        assert result.status == "review"
        assert result.nutrients_per_serving["energy_kcal"] == pytest.approx(141.75)


def test_plain_shiitake_uses_traceable_fresh_estimate():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find(name="香菇")

    assert profile is not None
    assert profile.energy_kcal == 34
    assert profile.saturated_fat_g == 0.04
    assert profile.trans_fat_g == 0
    assert profile.source_type == "reference_other"
    assert "鲜香菇" in profile.source
    assert "fdc.nal.usda.gov/food-details/169242" in profile.source_url

    result = calculate_recipe(
        Recipe("香菇小菜", (IngredientAmount("香菇", 28.35),)), repository
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["energy_kcal"] > 0


def test_corn_kernel_spellings_use_three_form_average_with_source_ids():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name in ("栗米粒", "粟米粒"):
        profile = repository.find("TTF0058", name)
        assert profile is not None
        assert profile.energy_kcal == 91.619
        assert profile.sodium_mg == 64.667
        assert profile.trans_fat_g == 0
        assert profile.source_type == "reference_other"
        assert "AFCD3_F003209" in profile.source_food_id
        assert "AFCD3_F003202" in profile.source_food_id
        assert "AFCD3_F003220" in profile.source_food_id
        result = calculate_recipe(
            Recipe("玉米小菜", (IngredientAmount(name, 28.35, "TTF0058"),)),
            repository,
        )
        assert result.status == "review"


def test_plain_starch_uses_corn_and_potato_starch_average_despite_reused_code():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("DTL0006", "生粉")

    assert profile is not None
    assert profile.energy_kcal == 345.235
    assert profile.protein_g == 0.45
    assert profile.total_fat_g == 0.35
    assert profile.saturated_fat_g == 0.0645
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 84.4
    assert profile.sugars_g == 0
    assert profile.sodium_mg == 9.75
    assert profile.source_type == "reference_other"
    assert "AFCD3_F003988" in profile.source_food_id
    assert "DTU_FCDB11_1272" in profile.source_food_id
    assert "身份" in repository.correction_notes["生粉"]

    result = calculate_recipe(
        Recipe("淀粉小菜", (IngredientAmount("生粉", 14.175, "DTL0006"),)),
        repository,
    )
    assert result.status == "review"


def test_beef_brisket_cut_uses_four_same_cut_reference_profiles():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("MCK0050", "牛坑腩切")

    assert profile is not None
    assert profile.energy_kcal == 206.75
    assert profile.protein_g == 19.125
    assert profile.total_fat_g == 14.4525
    assert profile.saturated_fat_g == 5.255
    assert profile.trans_fat_g == 0.4275
    assert profile.available_carbohydrate_g == 0
    assert profile.sugars_g == 0
    assert profile.sodium_mg == 55
    assert profile.source_type == "reference_other"
    for food_id in ("NZ2024_M1045", "NZ2024_M1046", "NZ2024_M1155", "NZ2024_M1156"):
        assert food_id in profile.source_food_id
    assert "脂肪" in repository.correction_notes["牛坑腩切"]

    result = calculate_recipe(
        Recipe("牛腩小菜", (IngredientAmount("牛坑腩切", 155.925, "MCK0050"),)),
        repository,
    )
    assert result.status == "review"


def test_generic_pork_names_use_raw_pork_average_not_plant_meat():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name, code in (
        ("豚肉", "HK0-0416"),
        ("豬肉", "HK0-2004"),
        ("豬肉粒", "HK0-2004"),
        ("豬肉絲", "MCK0054"),
    ):
        profile = repository.find(code, name)
        assert profile is not None
        assert profile.energy_kcal == 172.801
        assert profile.protein_g == 21.367
        assert profile.total_fat_g == 9.733
        assert profile.saturated_fat_g == 3.617
        assert profile.trans_fat_g == 0.05149
        assert profile.available_carbohydrate_g == 0
        assert profile.sugars_g == 0
        assert profile.sodium_mg == 52.333
        assert profile.source_type == "reference_other"
        for food_id in ("AFCD3_F007037", "AFCD3_F007030", "AFCD3_F007057"):
            assert food_id in profile.source_food_id
        assert "肥瘦" in repository.correction_notes[name]


def test_pork_slices_use_raw_pork_average_not_omnipork():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-2575", "豬肉片")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (172.801, 21.367, 9.733, 3.617, 0.05149, 0, 0, 52.333)
    assert "AFCD3_F007037" in profile.source_food_id
    assert "OmniPork" in repository.correction_notes[normalize_name("豬肉片")]

    result = calculate_recipe(
        Recipe("豬肉片小菜", (IngredientAmount("豬肉片", 99.225, "HK0-2575"),)),
        repository,
    )
    assert result.status == "review"


def test_counted_chicken_nuggets_use_traceable_battered_nugget_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-0000", "麥樂雞")

    assert profile is not None
    assert profile.energy_kcal == 235
    assert profile.protein_g == 12.35
    assert profile.total_fat_g == 14.15
    assert profile.saturated_fat_g == 2.6
    assert profile.trans_fat_g == 0.1
    assert profile.available_carbohydrate_g == 13.8
    assert profile.sugars_g == 2.03
    assert profile.sodium_mg == 497
    assert profile.source_type == "reference_other"
    assert "NZ2024_N47" in profile.source_food_id
    assert "USDA_FDC_2610020" in profile.source_food_id
    assert not profile.missing_nutrients[:8]
    assert "未熟" in repository.correction_notes["麥樂雞"]

    result = calculate_recipe(
        Recipe("麥樂雞", (IngredientAmount("麥樂雞", 80, "HK0-0000"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["energy_kcal"] == 188


def test_egg_liquid_names_use_raw_whole_egg_only_as_review_estimate():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name in ("蛋漿", "雞蛋漿"):
        profile = repository.find("HK0-0338", name)
        assert profile is not None
        assert profile.energy_kcal == 127
        assert profile.protein_g == 12.6
        assert profile.total_fat_g == 8.5
        assert profile.saturated_fat_g == 2.3
        assert profile.trans_fat_g == 0.00988
        assert profile.available_carbohydrate_g == 0.3
        assert profile.sugars_g == 0.3
        assert profile.sodium_mg == 150
        assert profile.source_food_id == "070900F003729"
        assert profile.source_type == "reference_other"
        assert "加水" in repository.correction_notes[name]

        result = calculate_recipe(
            Recipe("蛋菜", (IngredientAmount(name, 100, "HK0-0338"),)),
            repository,
        )
        assert result.status == "review"
        assert result.nutrients_per_serving["energy_kcal"] == 127


def test_chicken_powder_uses_disclosed_analogue_trans_fat_estimate():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name in (
        "调味雞粉(家樂)1kg*12包",
        "12X1KG家樂牌調味雞粉(包裝)",
        "家樂牌調味雞粉(包裝)",
        "雞粉",
    ):
        profile = repository.find(name=name)
        assert profile is not None
        assert profile.trans_fat_g == 0
        assert "trans_fat_g" not in profile.missing_nutrients
        note = repository.correction_notes[normalize_name(name)]
        assert "Edamam" in note
        assert "非品牌實測" in note

        result = calculate_recipe(
            Recipe("雞粉測試", (IngredientAmount(name, 10),)), repository
        )
        assert result.status == "review"
        assert result.nutrients_per_serving["sodium_mg"] == 1686


def test_raw_minced_beef_uses_three_fat_grade_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-0626", "免治牛肉")

    assert profile is not None
    assert profile.energy_kcal == 160.771
    assert profile.protein_g == 22.6
    assert profile.total_fat_g == 7.8
    assert profile.saturated_fat_g == 3.443
    assert profile.trans_fat_g == 0.24817
    assert profile.available_carbohydrate_g == 0
    assert profile.sugars_g == 0
    assert profile.sodium_mg == 62.333
    assert profile.source_type == "reference_other"
    for food_id in ("AFCD3_F000666", "AFCD3_F000678", "AFCD3_F000655"):
        assert food_id in profile.source_food_id
    assert "肥瘦" in repository.correction_notes["免治牛肉"]

    result = calculate_recipe(
        Recipe("免治牛肉小菜", (IngredientAmount("免治牛肉", 100, "HK0-0626"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["energy_kcal"] == 160.771


def test_beef_mince_alias_does_not_use_cooked_diced_beef_profile():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-0626", "牛肉碎")

    assert profile is not None
    assert profile.energy_kcal == 160.771
    assert profile.total_fat_g == 7.8
    assert profile.trans_fat_g == 0.24817
    assert "AFCD3_F000678" in profile.source_food_id
    assert "生免治牛肉" in repository.correction_notes["牛肉碎"]


def test_unspecified_meat_slices_and_shreds_use_review_pork_estimate_not_rabbit():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name, code in (("肉片", "HK0-2575"), ("肉絲", "SHK0001")):
        profile = repository.find(code, name)
        assert profile is not None
        assert profile.energy_kcal == 172.801
        assert profile.protein_g == 21.367
        assert profile.total_fat_g == 9.733
        assert profile.saturated_fat_g == 3.617
        assert profile.trans_fat_g == 0.05149
        assert profile.available_carbohydrate_g == 0
        assert profile.sugars_g == 0
        assert profile.sodium_mg == 52.333
        assert "AFCD3_F007057" in profile.source_food_id
        assert "豬肉身份待確認" in repository.correction_notes[name]

        result = calculate_recipe(
            Recipe("肉菜", (IngredientAmount(name, 100, code),)), repository
        )
        assert result.status == "review"


def test_chicken_pieces_use_raw_breast_and_thigh_average_not_chicken_floss():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-2518", "雞肉粒")

    assert profile is not None
    assert profile.energy_kcal == 108.5
    assert profile.protein_g == 19.7
    assert profile.total_fat_g == 3.25
    assert profile.saturated_fat_g == 0.975
    assert profile.trans_fat_g == 0.015
    assert profile.available_carbohydrate_g == 0
    assert profile.sugars_g == 0
    assert profile.sodium_mg == 98
    assert profile.source_type == "reference_other"
    assert "NZ2024_M10007" in profile.source_food_id
    assert "NZ2024_M10013" in profile.source_food_id
    assert "部位" in repository.correction_notes["雞肉粒"]

    result = calculate_recipe(
        Recipe("雞肉粒小菜", (IngredientAmount("雞肉粒", 100, "HK0-2518"),)),
        repository,
    )
    assert result.status == "review"


def test_fish_fillet_names_use_traceable_raw_fillet_estimate_not_breaded_fish():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name, code in (("魚柳", "HKO1771"), ("魚柳粒", "HK0-3223")):
        profile = repository.find(code, name)
        assert profile is not None
        assert profile.energy_kcal == 96.678
        assert profile.protein_g == 17.1
        assert profile.total_fat_g == 3.1
        assert profile.saturated_fat_g == 0.935
        assert profile.trans_fat_g == 0.053455
        assert profile.available_carbohydrate_g == 0
        assert profile.sugars_g == 0
        assert profile.sodium_mg == 84
        assert profile.source_type == "reference_other"
        assert "AFCD3_F000402" in profile.source_food_id
        assert "AFCD3_F009163" in profile.source_food_id
        assert "魚種" in repository.correction_notes[name]
        result = calculate_recipe(
            Recipe("魚柳小菜", (IngredientAmount(name, 100, code),)), repository
        )
        assert result.status == "review"

    vegan_fillet = repository.find(name="素魚柳")
    assert vegan_fillet is not None
    assert vegan_fillet.ingredient_code == "REVIEW_202609_0018"
    assert (
        vegan_fillet.energy_kcal,
        vegan_fillet.protein_g,
        vegan_fillet.total_fat_g,
        vegan_fillet.saturated_fat_g,
        vegan_fillet.trans_fat_g,
        vegan_fillet.available_carbohydrate_g,
        vegan_fillet.sugars_g,
        vegan_fillet.sodium_mg,
    ) == (284, 16.75, 14.2, 6.5, 0, 22.25, 2.85, 594.5)
    assert "vegefarm.com.tw" in vegan_fillet.source_url
    assert "vegue.me" in vegan_fillet.source_url


def test_pumpkin_puree_uses_plain_pumpkin_only_as_review_estimate():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find(name="南瓜蓉")
    assert profile is not None
    assert profile.energy_kcal == 31
    assert profile.protein_g == 1.2
    assert profile.total_fat_g == 0
    assert profile.saturated_fat_g == 0
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 6.7
    assert profile.sugars_g == 6
    assert profile.sodium_mg == 0
    assert profile.source_food_id == "AFCD3_F007555"
    assert "純南瓜" in repository.correction_notes["南瓜蓉"]
    result = calculate_recipe(
        Recipe("南瓜蓉小菜", (IngredientAmount("南瓜蓉", 100),)), repository
    )
    assert result.status == "review"


def test_fatty_beef_slices_use_fat_inclusive_raw_beef_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name in ("肥牛片", "肥牛"):
        profile = repository.find("HK0-0862", name)
        assert profile is not None
        assert profile.energy_kcal == 234.648
        assert profile.protein_g == 20
        assert profile.total_fat_g == 17.2
        assert profile.saturated_fat_g == 6.66
        assert profile.trans_fat_g == 0.652543
        assert profile.available_carbohydrate_g == 0
        assert profile.sugars_g == 0
        assert profile.sodium_mg == 55
        assert profile.source_type == "reference_other"
        for food_id in ("AFCD3_F000527", "AFCD3_F000851", "NZ2024_M1155"):
            assert food_id in profile.source_food_id
        assert "肥瘦" in repository.correction_notes[name]
        result = calculate_recipe(
            Recipe("肥牛小菜", (IngredientAmount(name, 100, "HK0-0862"),)),
            repository,
        )
        assert result.status == "review"


def test_beef_slices_use_raw_chuck_fat_grade_average_not_empty_correction():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for code in ("HK0-3235", "HK0-1779"):
        profile = repository.find(code, "牛肉片")
        assert profile is not None
        assert profile.energy_kcal == 152.008
        assert profile.protein_g == 22.35
        assert profile.total_fat_g == 6.9
        assert profile.saturated_fat_g == 2.7
        assert profile.trans_fat_g == 0.29138
        assert profile.available_carbohydrate_g == 0
        assert profile.sugars_g == 0
        assert profile.sodium_mg == 60
        assert profile.source_type == "reference_other"
        assert "AFCD3_F000523" in profile.source_food_id
        assert "AFCD3_F000527" in profile.source_food_id
        assert "部位" in repository.correction_notes["牛肉片"]
        result = calculate_recipe(
            Recipe("牛肉片小菜", (IngredientAmount("牛肉片", 100, code),)),
            repository,
        )
        assert result.status == "review"


def test_unspecified_dark_soy_uses_documented_hong_kong_proxy_not_reused_code():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for code in ("A10-1269", "DTL0040"):
        profile = repository.find(code, "老抽/40斤")
        assert profile is not None
        assert profile.energy_kcal == 120
        assert profile.protein_g == 10
        assert profile.total_fat_g == 0
        assert profile.saturated_fat_g == 0
        assert profile.trans_fat_g == 0
        assert profile.available_carbohydrate_g == 14
        assert profile.sugars_g == 12
        assert profile.sodium_mg == 6340
        assert profile.source_type == "reference_other"
        assert "shop.lkk.com/products/premium-dark-sauce-500ml" in profile.source_url
        assert "每5g" in repository.correction_notes[normalize_name("老抽/40斤")]
        result = calculate_recipe(
            Recipe("老抽菜", (IngredientAmount("老抽/40斤", 5, code),)),
            repository,
        )
        assert result.status == "review"
        assert result.nutrients_per_serving["sodium_mg"] == 317


def test_choy_sun_oyster_sauce_uses_hong_kong_label_as_review_reference():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("DTL0158", "蠔油/財神蠔油")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (120, 0.6, 0, 0, 0, 29, 24, 4580)
    assert profile.source_type == "reference_other"
    assert "shop.lkk.com/products/choy-sun-oyster-sauce-510g" in profile.source_url
    assert "每10g" in repository.correction_notes[normalize_name("蠔油/財神蠔油")]

    result = calculate_recipe(
        Recipe("蠔油菜", (IngredientAmount("蠔油/財神蠔油", 10, "DTL0158"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["sodium_mg"] == 458

    distinct_product = repository.find("DTL0158", "錦珍財神蠔油")
    assert distinct_product is not None
    assert distinct_product.ingredient_name == "錦珍財神蠔油"
    assert distinct_product.source_food_id == "AFCD3_F008026;LKK_HK_CHOY_SUN_510G"


def test_ambiguous_kum_chun_choy_sun_oyster_sauce_uses_full_profile_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-0101", "錦珍財神蠔油")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (116.285851, 1.7, 0.5, 0.08, 0, 25, 19.8, 4185)
    assert profile.source_type == "reference_other"
    assert "foodstandards.gov.au" in profile.source_url
    assert "shop.lkk.com/products/choy-sun-oyster-sauce-510g" in profile.source_url
    assert "身份未確認" in repository.correction_notes[normalize_name("錦珍財神蠔油")]
    assert "83kcal" in repository.correction_notes[normalize_name("錦珍財神蠔油")]

    result = calculate_recipe(
        Recipe("蠔油菜", (IngredientAmount("錦珍財神蠔油", 10, "HK0-0101"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["sodium_mg"] == 418.5


def test_unspecified_mushroom_powder_uses_two_hong_kong_label_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("REVIEW_202609_0003", "鮮菇粉")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (250, 2, 5, 5, 0, 45, 25, 14850)
    assert profile.source_type == "reference_other"
    assert "PNSHK-483128-nutrition-zoom.jpg" in profile.source_url
    assert "PNSHK-338542-nutrition-zoom.jpg" in profile.source_url
    assert "每1g" in repository.correction_notes[normalize_name("鮮菇粉")]
    assert "四捨五入" in repository.correction_notes[normalize_name("鮮菇粉")]

    result = calculate_recipe(
        Recipe("鮮菇粉小菜", (IngredientAmount("鮮菇粉", 1, "REVIEW_202609_0003"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["sodium_mg"] == 148.5


def test_vegetarian_mushroom_powder_uses_review_average_not_dried_mushroom():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-2651", "素菇粉")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (250, 2, 5, 5, 0, 45, 25, 14850)
    assert profile.source_type == "reference_other"
    assert "PNSHK_483128" in profile.source_food_id
    assert "PNSHK_338542" in profile.source_food_id
    assert "四捨五入" in repository.correction_notes[normalize_name("素菇粉")]

    result = calculate_recipe(
        Recipe("素菇粉小菜", (IngredientAmount("素菇粉", 8.505, "HK0-2651"),)),
        repository,
    )
    assert result.status == "review"
    assert round(result.nutrients_per_serving["sodium_mg"], 4) == 1262.9925


def test_winter_shiitake_names_use_fresh_estimate_pending_purchase_check():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name in ("冬菇", "冬菇片", "冬菇碎"):
        profile = repository.find("HK0-1465", name)
        assert profile is not None
        assert (
            profile.energy_kcal,
            profile.protein_g,
            profile.total_fat_g,
            profile.saturated_fat_g,
            profile.trans_fat_g,
            profile.available_carbohydrate_g,
            profile.sugars_g,
            profile.sodium_mg,
        ) == (34, 2.24, 0.49, 0.04, 0, 4.29, 2.38, 9)
        assert profile.source_type == "reference_other"
        assert "169242" in profile.source_url
        assert "鮮" in repository.correction_notes[normalize_name(name)]
        result = calculate_recipe(
            Recipe("冬菇菜", (IngredientAmount(name, 14.175, "HK0-1465"),)),
            repository,
        )
        assert result.status == "review"


def test_shredded_winter_shiitake_uses_fresh_reference_as_review_estimate():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("DTL0462", "冬菇絲")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (34, 2.24, 0.49, 0.04, 0, 4.29, 2.38, 9)
    assert "USDA_FDC_169242" in profile.source_food_id
    assert "MEXT_08039_SAT" in profile.source_food_id
    assert "乾貨" in repository.correction_notes[normalize_name("冬菇絲")]

    result = calculate_recipe(
        Recipe("冬菇絲小菜", (IngredientAmount("冬菇絲", 14.175, "DTL0462"),)),
        repository,
    )
    assert result.status == "review"


def test_carrot_juice_uses_two_traceable_references_pending_supplier_check():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find(name="甘筍汁")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (35, 0.775, 0.075, 0.015, 0, 7.725, 5.15, 81.25)
    assert profile.source_type == "reference_other"
    assert "kagome.hk" in profile.source_url
    assert "170491" in profile.source_url
    assert "1ml" in repository.correction_notes[normalize_name("甘筍汁")]

    result = calculate_recipe(
        Recipe("甘筍汁小菜", (IngredientAmount("甘筍汁", 5.67),)), repository
    )
    assert result.status == "review"


def test_unspecified_bread_bun_uses_two_full_commercial_label_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find(name="麵包胚")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (254.022989, 9.8659, 2.95977, 0.98659, 0, 44.893678, 4.808429, 459.961686)
    assert profile.source_type == "reference_other"
    assert "886706" in profile.source_url
    assert "hamburger-buns-4091533" in profile.source_url
    assert "非採購品" in repository.correction_notes[normalize_name("麵包胚")]

    result = calculate_recipe(
        Recipe("漢堡包", (IngredientAmount("麵包胚", 51.5),)), repository
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["energy_kcal"] > 0


def test_unspecified_sweet_pepper_uses_three_raw_colour_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find(name="甜椒")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (22.321224, 1.033333, 0.266667, 0, 0, 3.733333, 3.733333, 2)
    assert profile.source_type == "reference_other"
    assert "070304F002239" in profile.source_food_id
    assert "070304F002247" in profile.source_food_id
    assert "AFCD3_F010259" in profile.source_food_id
    assert "顏色" in repository.correction_notes[normalize_name("甜椒")]

    result = calculate_recipe(
        Recipe("甜椒小菜", (IngredientAmount("甜椒", 100),)), repository
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["energy_kcal"] == 22.321224


def test_tofu_puffs_use_two_manufacturer_average_not_solid_fried_tofu():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-1380", "豆卜")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == pytest.approx(
        (278.071429, 20.1, 19.871429, 5.728571, 0, 3.992857, 0.714286, 21.292857),
        abs=0.000001,
    )
    assert "HAKKA_5127" in profile.source_food_id
    assert "CHANGSHING_FRIED_PUFFS" in profile.source_food_id
    assert "少於1g" in repository.correction_notes[normalize_name("豆卜")]
    fried = repository.find("HK0-1380", "炸豆腐")
    assert fried is not None
    assert (
        fried.energy_kcal,
        fried.protein_g,
        fried.total_fat_g,
        fried.saturated_fat_g,
        fried.trans_fat_g,
        fried.available_carbohydrate_g,
        fried.sugars_g,
        fried.sodium_mg,
    ) == (270, 18.8, 20.2, 2.92, 0, 4.96, 2.72, 16)
    assert fried.source_food_id == "USDA_FDC_172451"
    assert fried.source_type == "reference_other"
    assert fried.energy_kcal != profile.energy_kcal
    assert "推定" in repository.correction_notes[normalize_name("炸豆腐")]

    fried_result = calculate_recipe(
        Recipe("炸豆腐小菜", (IngredientAmount("炸豆腐", 56.7, "HK0-1380"),)),
        repository,
    )
    assert fried_result.status == "review"
    assert fried_result.nutrients_per_serving["energy_kcal"] == pytest.approx(153.09)

    result = calculate_recipe(
        Recipe("豆卜小菜", (IngredientAmount("豆卜", 56.7, "HK0-1380"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["energy_kcal"] > 0


def test_plain_minced_garlic_uses_raw_garlic_reference_without_matching_fried_garlic():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("BCPN-9014", "蒜蓉")
    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (149, 6.36, 0.5, 0.089, 0, 31, 1, 17)
    assert profile.source_food_id == "USDA_FDC_169230"
    assert profile.source_type == "reference_other"
    assert "生鮮" in repository.correction_notes[normalize_name("蒜蓉")]
    assert repository.find(name="炸蒜容").energy_kcal != profile.energy_kcal

    result = calculate_recipe(
        Recipe("蒜蓉小菜", (IngredientAmount("蒜蓉", 2.835, "BCPN-9014"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["available_carbohydrate_g"] == pytest.approx(0.87885)


def test_coarse_fried_noodles_use_historical_local_trans_fat_proxy_for_review():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find("HK0-1743", "粗炒")
    assert profile is not None
    assert profile.trans_fat_g == 0.028
    assert profile.source_type == "reference_other"
    assert "annex4.pdf" in profile.source_url
    assert "肉絲炒麵" in repository.correction_notes[normalize_name("粗炒")]
    result = calculate_recipe(
        Recipe("上海粗炒", (IngredientAmount("粗炒", 100, "HK0-1743"),)), repository
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["trans_fat_g"] == 0.028
