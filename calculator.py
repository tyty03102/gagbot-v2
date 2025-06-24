import discord
from discord import app_commands
import math

class GardenCalculator:
    def __init__(self):
        self.crop_base_values = {
            "apple": {"min_value": 248, "default_weight": 2.85, "k_value": 30.53},
            "bamboo": {"min_value": 3610, "default_weight": 3.8, "k_value": 250},
            "banana": {"min_value": 1579, "default_weight": 1.425, "k_value": 777.77},
            "beanstalk": {"min_value": 25270, "default_weight": 9.5, "k_value": 280},
            "bee balm": {"min_value": 16245, "default_weight": 0.94, "k_value": 18033.333},
            "bendboo": {"min_value": 138988, "default_weight": 17.09, "k_value": 478.5},
            "blood banana": {"min_value": 5415, "default_weight": 1.42, "k_value": 2670},
            "blueberry": {"min_value": 18, "default_weight": 0.17, "k_value": 500},
            "cacao": {"min_value": 10830, "default_weight": 7.6, "k_value": 187.5},
            "cactus": {"min_value": 3069, "default_weight": 6.65, "k_value": 69.4},
            "candy blossom": {"min_value": 90250, "default_weight": 2.85, "k_value": 11111.1112},
            "candy sunflower": {"min_value": 72200, "default_weight": 1.428, "k_value": 35413},
            "carrot": {"min_value": 18, "default_weight": 0.24, "k_value": 275},
            "celestiberry": {"min_value": 9025, "default_weight": 1.9, "k_value": 2500},
            "cherry blossom": {"min_value": 550, "default_weight": 1.0, "k_value": 1.0},  # Not yet implemented in game
            "chocolate carrot": {"min_value": 9960, "default_weight": 0.262, "k_value": 145096},
            "coconut": {"min_value": 361, "default_weight": 13.31, "k_value": 2.04},
            "cocovine": {"min_value": 60166, "default_weight": 13.3, "k_value": 340},
            "corn": {"min_value": 36, "default_weight": 1.9, "k_value": 10},
            "cranberry": {"min_value": 1805, "default_weight": 0.95, "k_value": 2000},
            "crocus": {"min_value": 27075, "default_weight": 0.285, "k_value": 333333},
            "cursed fruit": {"min_value": 15000, "default_weight": 22.9, "k_value": 28.6},
            "daffodil": {"min_value": 903, "default_weight": 0.16, "k_value": 25000},
            "dandelion": {"min_value": 45125, "default_weight": 3.79, "k_value": 3130},
            "dragon fruit": {"min_value": 4287, "default_weight": 11.38, "k_value": 32.990001},
            "dragon pepper": {"min_value": 80000, "default_weight": 5.69, "k_value": 2470},
            "durian": {"min_value": 6317, "default_weight": 7.6, "k_value": 109.37},
            "easter egg": {"min_value": 2256, "default_weight": 2.85, "k_value": 277.825},
            "eggplant": {"min_value": 6769, "default_weight": 4.75, "k_value": 300},
            "ember lily": {"min_value": 50138, "default_weight": 11.4, "k_value": 385.6},
            "foxglove": {"min_value": 18050, "default_weight": 1.9, "k_value": 5000},
            "glowshroom": {"min_value": 271, "default_weight": 0.7, "k_value": 532.5},
            "grape": {"min_value": 7085, "default_weight": 2.85, "k_value": 872},
            "hive fruit": {"min_value": 55955, "default_weight": 7.59, "k_value": 969},
            "honeysuckle": {"min_value": 90250, "default_weight": 11.4, "k_value": 694.3},
            "lavender": {"min_value": 22563, "default_weight": 0.25, "k_value": 361008},
            "lemon": {"min_value": 500, "default_weight": 1.0, "k_value": 1.0},  # Not yet implemented in game
            "lilac": {"min_value": 31588, "default_weight": 2.846, "k_value": 3899},
            "lotus": {"min_value": 15343, "default_weight": 18.99, "k_value": 42.5},
            "lumira": {"min_value": 76713, "default_weight": 5.69, "k_value": 2362.5},
            "mango": {"min_value": 5866, "default_weight": 14.28, "k_value": 28.89},
            "manuka flower": {"min_value": 22563, "default_weight": 0.289, "k_value": 270000},
            "mint": {"min_value": 4738, "default_weight": 0.95, "k_value": 5230},
            "moon blossom": {"min_value": 60166, "default_weight": 2.85, "k_value": 7407.4},
            "moon mango": {"min_value": 45125, "default_weight": 14.25, "k_value": 222.22},
            "moon melon": {"min_value": 16245, "default_weight": 7.6, "k_value": 281.2},
            "moonflower": {"min_value": 8574, "default_weight": 1.9, "k_value": 2381},
            "moonglow": {"min_value": 18050, "default_weight": 6.65, "k_value": 408.45},
            "mushroom": {"min_value": 136278, "default_weight": 25.9, "k_value": 241.6},
            "nectar thorn": {"min_value": 30083, "default_weight": 5.76, "k_value": 906},
            "nectarine": {"min_value": 35000, "default_weight": 2.807, "k_value": 4440},
            "nectarshade": {"min_value": 45125, "default_weight": 0.75, "k_value": 78500},
            "nightshade": {"min_value": 3159, "default_weight": 0.48, "k_value": 13850},
            "orange tulip": {"min_value": 751, "default_weight": 0.05, "k_value": 300000},
            "papaya": {"min_value": 903, "default_weight": 2.86, "k_value": 111.11},
            "passionfruit": {"min_value": 3204, "default_weight": 2.867, "k_value": 395},
            "peach": {"min_value": 271, "default_weight": 1.9, "k_value": 75},
            "pear": {"min_value": 451, "default_weight": 2.85, "k_value": 55.5},
            "pepper": {"min_value": 7220, "default_weight": 4.75, "k_value": 320},
            "pineapple": {"min_value": 1805, "default_weight": 2.85, "k_value": 222.5},
            "pink lily": {"min_value": 58663, "default_weight": 5.699, "k_value": 1806.5},
            "pumpkin": {"min_value": 3069, "default_weight": 6.9, "k_value": 64},
            "purple dahlia": {"min_value": 67688, "default_weight": 11.4, "k_value": 522},
            "raspberry": {"min_value": 90, "default_weight": 0.71, "k_value": 177.5},
            "red lollipop": {"min_value": 45102, "default_weight": 3.799, "k_value": 3125},
            "rose": {"min_value": 4513, "default_weight": 0.95, "k_value": 5000},
            "soul fruit": {"min_value": 6994, "default_weight": 23.75, "k_value": 12.4},
            "starfruit": {"min_value": 13538, "default_weight": 2.85, "k_value": 1666.6},
            "strawberry": {"min_value": 14, "default_weight": 0.29, "k_value": 175},
            "succulent": {"min_value": 22563, "default_weight": 4.75, "k_value": 1000},
            "sugar apple": {"min_value": 43320, "default_weight": 8.55, "k_value": 592.6},
            "suncoil": {"min_value": 72200, "default_weight": 9.5, "k_value": 800},
            "sunflower": {"min_value": 144000, "default_weight": 15.65, "k_value": 587.8},
            "tomato": {"min_value": 27, "default_weight": 0.44, "k_value": 120},
            "venus fly trap": {"min_value": 40612, "default_weight": 9.5, "k_value": 450},
            "violet corn": {"min_value": 45125, "default_weight": 2.85, "k_value": 5555.555},
            "watermelon": {"min_value": 2708, "default_weight": 7.3, "k_value": 61.25},
        }

        self.growth_mutations = {
            "default": 1,
            "gold": 20,
            "golden": 20,
            "rainbow": 50
        }

        self.temperature_mutations = {
            "default": 0,
            "wet": 1,
            "chilled": 1,
            "frozen": 9
        }

        self.environmental_mutations = {
            "chocolate": 1,
            "moonlit": 1,
            "pollinated": 2,
            "bloodlit": 3,
            "plasma": 4,
            "honey glazed": 4,
            "heavenly": 4,
            "zombified": 24,
            "shocked": 99,
            "celestial": 119,
            "disco": 124,
            "voidtouched": 134,
            "dawnbound": 149
        }

    def get_environmental_mutations(self) -> list[str]:
        """Returns a list of all available environmental mutation names."""
        return sorted(self.environmental_mutations.keys())

    def get_default_weights(self) -> dict[str, float]:
        """Returns a dictionary of all plants and their default weights."""
        return {plant: data["default_weight"] for plant, data in self.crop_base_values.items()}

    def calculate_crop_value(self, crop: str, growth_mutation: str, temp_mutation: str, environmental_mutations: list[str], weight_kg: float) -> dict:
        """Calculate the total value of a crop based on its type, mutations, and weight."""
        if weight_kg <= 0:
            return {"error": "Weight must be greater than 0"}

        crop_info = self.crop_base_values.get(crop.lower())
        if not crop_info:
            return {"error": f"Invalid crop type: {crop}. Supported crops: {', '.join(self.crop_base_values.keys())}"}

        initial_value_base = crop_info["min_value"]
        if weight_kg > crop_info["default_weight"]:
            calculated_base_from_k = crop_info["k_value"] * (weight_kg ** 2)
            initial_value_base = max(calculated_base_from_k, crop_info["min_value"])

        growth_multiplier = self.growth_mutations.get(growth_mutation.lower())
        if growth_multiplier is None:
            return {"error": f"Invalid growth mutation: {growth_mutation}. Supported: {', '.join(self.growth_mutations.keys())}"}

        temp_additive = self.temperature_mutations.get(temp_mutation.lower())
        if temp_additive is None:
            return {"error": f"Invalid temperature mutation: {temp_mutation}. Supported: {', '.join(self.temperature_mutations.keys())}"}

        environmental_additive_sum = 0
        for env_mut in environmental_mutations:
            value = self.environmental_mutations.get(env_mut.lower())
            if value is None:
                return {"error": f"Invalid environmental mutation: {env_mut}. Supported: {', '.join(self.environmental_mutations.keys())}"}
            environmental_additive_sum += value

        total_additive_factor = 1 + temp_additive + environmental_additive_sum

        total_value = initial_value_base * growth_multiplier * total_additive_factor
        
        return {
            "crop": crop,
            "growth_mutation": growth_mutation,
            "temp_mutation": temp_mutation,
            "environmental_mutations": environmental_mutations,
            "weight_kg": weight_kg,
            "total_value": math.ceil(total_value)  # Changed to math.ceil for accurate rounding
        }

    def format_calculation_result(self, result: dict) -> discord.Embed:
        """Format the calculation result into a Discord embed."""
        if "error" in result:
            embed = discord.Embed(
                title="❌ Calculation Error",
                description=result["error"],
                color=discord.Color.red()
            )
            return embed
        
        embed = discord.Embed(
            title=f"🍎 {result['crop'].title()} Value Calculation",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 Crop Details",
            value=f"• Crop: {result['crop'].title()}\n"
                  f"• Weight (kg): {result['weight_kg']}",
            inline=False
        )
        
        embed.add_field(
            name="🧬 Mutations",
            value=f"• Growth: {result['growth_mutation'].title()}\n"
                  f"• Temperature: {result['temp_mutation'].title()}\n"
                  f"• Environmental: {', '.join([m.title() for m in result['environmental_mutations']]) if result['environmental_mutations'] else 'None'}",
            inline=False
        )
        
        # Format the total value with commas
        formatted_value = "{:,}".format(result['total_value'])
        
        embed.add_field(
            name="💰 Total Estimated Value",
            value=f"**{formatted_value} coins**",
            inline=False
        )
        
        embed.set_footer(text="Grow A Garden Crop Value Bot")
        return embed

# Create a global instance of the calculator
calculator = GardenCalculator() 