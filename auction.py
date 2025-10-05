import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncio
import datetime
from typing import Dict, Optional, List, Literal
import sys
import os

# Add the parent directory to sys.path to import from utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.auction_manager import AuctionManager, Auction

class BidButton(Button):
    def __init__(self, auction_id: int, manager: AuctionManager):
        self.auction_id = auction_id
        self.manager = manager
        super().__init__(label="Place Bid", style=discord.ButtonStyle.green)
    
    async def callback(self, interaction: discord.Interaction):
        auction = self.manager.get_auction(self.auction_id)
        if not auction:
            await interaction.response.send_message("This auction no longer exists.", ephemeral=True)
            return
        
        if auction.ended:
            await interaction.response.send_message("This auction has ended.", ephemeral=True)
            return
        
        # Get the user who clicked the button
        user = interaction.user
        current_bid = auction.highest_bid
        
        # Calculate the new bid
        new_bid = current_bid + auction.bid_increment
        
        # Create a proper Modal class outside of this method
        # Create and show a BidModal
        modal = BidModal(auction, self.manager, user, new_bid)
        await interaction.response.send_modal(modal)


# Define the BidModal class properly
class BidModal(discord.ui.Modal):
    def __init__(self, auction, manager, user, min_bid):
        super().__init__(title=f"Place Bid on {auction.item_name}")
        self.auction = auction
        self.manager = manager
        self.user = user
        self.min_bid = min_bid
        
        # Add the bid amount input
        self.bid_amount = discord.ui.TextInput(
            label=f"Enter bid amount (min: {min_bid} {auction.currency})",
            placeholder=f"Enter a number greater than or equal to {min_bid}",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.bid_amount)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.bid_amount.value)
            if amount < self.min_bid:
                await interaction.response.send_message(
                    f"Your bid must be at least {self.min_bid} {self.auction.currency}.", 
                    ephemeral=True
                )
                return
            
            # Update the auction with the new bid
            success = self.auction.place_bid(self.user.id, self.user.name, amount)
            if success:
                # Update the auction message
                view = AuctionView(self.auction.id, self.manager)
                embed = self.manager.create_auction_embed(self.auction)
                
                # Get the original message
                channel = interaction.channel
                message = await channel.fetch_message(self.auction.message_id)
                await message.edit(embed=embed, view=view)
                
                # Just send confirmation to the bidder without posting an announcement message
                await interaction.response.send_message(
                    f"Bid of {amount} {self.auction.currency} placed successfully! The auction has been updated.", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Failed to place bid. The auction may have ended or your bid is no longer high enough.", 
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number for your bid.", 
                ephemeral=True
            )


class AuctionView(View):
    def __init__(self, auction_id: int, manager: AuctionManager):
        super().__init__(timeout=None)
        self.auction_id = auction_id
        self.manager = manager
        self.add_item(BidButton(auction_id, manager))


class CancelButton(Button):
    def __init__(self, auction_id: int, manager: AuctionManager):
        self.auction_id = auction_id
        self.manager = manager
        super().__init__(label="Cancel Auction", style=discord.ButtonStyle.red)
    
    async def callback(self, interaction: discord.Interaction):
        # Check if user has admin permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You don't have permission to cancel auctions.", 
                ephemeral=True
            )
            return
        
        auction = self.manager.get_auction(self.auction_id)
        if not auction:
            await interaction.response.send_message(
                "This auction no longer exists.", 
                ephemeral=True
            )
            return
        
        # Cancel the auction
        self.manager.end_auction(self.auction_id, cancelled=True)
        
        # Update the auction message
        embed = discord.Embed(
            title=f"Auction: {auction.item_name} [CANCELLED]",
            description="This auction has been cancelled by an administrator.",
            color=discord.Color.red()
        )
        
        # Get the original message
        channel = interaction.channel
        message = await channel.fetch_message(auction.message_id)
        await message.edit(embed=embed, view=None)
        
        await interaction.response.send_message(
            f"Auction for {auction.item_name} has been cancelled.", 
            ephemeral=True
        )
        
        # Announce the cancellation
        await channel.send(
            f"⚠️ **Auction Cancelled!** The auction for **{auction.item_name}** has been cancelled by {interaction.user.mention}."
        )


class AuctionCog(commands.GroupCog, group_name="auction"):
    def __init__(self, bot):
        self.bot = bot
        self.auction_manager = AuctionManager()
        self.check_auctions.start()
        super().__init__()
    
    def cog_unload(self):
        self.check_auctions.cancel()
    
    @tasks.loop(seconds=10)
    async def check_auctions(self):
        """Task to check for ended auctions"""
        ended_auctions = self.auction_manager.get_ended_auctions()
        for auction_id in ended_auctions:
            auction = self.auction_manager.get_auction(auction_id)
            if not auction:
                continue
            
            # Mark the auction as ended
            self.auction_manager.end_auction(auction_id)
            
            # Try to get the channel and message
            try:
                channel = self.bot.get_channel(auction.channel_id)
                if channel:
                    # Update the original auction message
                    message = await channel.fetch_message(auction.message_id)
                    if message:
                        embed = discord.Embed(
                            title=f"Auction: {auction.item_name} [ENDED]",
                            description=f"This auction has ended.",
                            color=discord.Color.blue()
                        )
                        
                        if auction.highest_bidder_id:
                            winner = self.bot.get_user(auction.highest_bidder_id)
                            winner_mention = winner.mention if winner else f"User ID: {auction.highest_bidder_id}"
                            
                            # Display winner according to anonymous setting
                            if auction.anonymous_bidding:
                                embed.add_field(
                                    name="Winner", 
                                    value="Anonymous",
                                    inline=True
                                )
                                
                                # Private notification to winner
                                try:
                                    if winner:
                                        await winner.send(f"🏆 Congratulations! You won the auction for **{auction.item_name}** with a bid of **{auction.highest_bid} {auction.currency}**!")
                                except:
                                    # Could not DM the winner
                                    pass
                                    
                                # Public announcement without mentioning the winner
                                await channel.send(
                                    f"🏆 **Auction Ended!** The auction for **{auction.item_name}** has ended with a winning bid of **{auction.highest_bid} {auction.currency}**. The winner has been notified."
                                )
                            else:
                                embed.add_field(
                                    name="Winner", 
                                    value=winner_mention,
                                    inline=True
                                )
                                
                                # Announce the winner publicly
                                await channel.send(
                                    f"🏆 **Auction Ended!** Congratulations to {winner_mention} for winning the **{auction.item_name}** with a bid of **{auction.highest_bid} {auction.currency}**!"
                                )
                                
                            embed.add_field(
                                name="Winning Bid", 
                                value=f"{auction.highest_bid} {auction.currency}",
                                inline=True
                            )
                        else:
                            embed.add_field(
                                name="Result", 
                                value="No bids were placed.",
                                inline=False
                            )
                            
                            # Announce no winner
                            await channel.send(
                                f"⏱️ **Auction Ended!** The auction for **{auction.item_name}** has ended with no bids."
                            )
                        
                        await message.edit(embed=embed, view=None)
            except Exception as e:
                print(f"Error processing ended auction {auction_id}: {e}")
    
    @check_auctions.before_loop
    async def before_check_auctions(self):
        await self.bot.wait_until_ready()
    
    # Slash command for starting auctions
    @app_commands.command(name="start", description="Start a new auction")
    @app_commands.describe(
        duration="Duration of the auction (e.g., 1h, 30m, 1d, 1d12h)",
        starting_bid="Initial bid amount",
        bid_increment="Minimum amount that each new bid must increase by",
        item_name="Name of the item being auctioned",
        currency="Type of currency (default: coins)",
        emblem_url="URL to an image for the auction (optional)",
        anonymous="Whether bidders remain anonymous (yes/no, default: no)",
        auto_delete_emblem="Whether to remove emblem after auction ends (yes/no, default: no)"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def auction_start(self, interaction: discord.Interaction, 
                           duration: str, 
                           starting_bid: int, 
                           bid_increment: int, 
                           item_name: str,
                           currency: str = "coins",
                           emblem_url: str = None, 
                           anonymous: Literal["yes", "no"] = "no", 
                           auto_delete_emblem: Literal["yes", "no"] = "no"):
        """Start a new auction"""
        # Parse duration
        try:
            duration_seconds = 0
            duration_copy = duration  # Keep a copy for error handling
            
            if 'd' in duration:
                days = int(duration.split('d')[0])
                duration_seconds += days * 86400
                duration = duration.split('d')[1]
            
            if 'h' in duration:
                hours = int(duration.split('h')[0])
                duration_seconds += hours * 3600
                duration = duration.split('h')[1]
            
            if 'm' in duration:
                minutes = int(duration.split('m')[0])
                duration_seconds += minutes * 60
            
            if duration_seconds == 0:
                raise ValueError("Invalid duration")
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Invalid duration format '{duration_copy}'. Use format like: 1h, 30m, 1d, 1d12h, etc.",
                ephemeral=True
            )
            return
        
        # Parse parameters
        anonymous_bidding = anonymous.lower() == "yes"
        auto_delete_emblem_bool = auto_delete_emblem.lower() == "yes"
        
        # Create the auction
        auction_id = self.auction_manager.create_auction(
            item_name=item_name,
            starting_bid=starting_bid,
            bid_increment=bid_increment,
            duration_seconds=duration_seconds,
            creator_id=interaction.user.id,
            channel_id=interaction.channel_id,
            currency=currency,
            emblem_url=emblem_url,
            anonymous_bidding=anonymous_bidding,
            auto_delete_emblem=auto_delete_emblem_bool
        )
        
        auction = self.auction_manager.get_auction(auction_id)
        
        # Create embed
        embed = self.auction_manager.create_auction_embed(auction)
        
        # Create view with bid button
        view = AuctionView(auction_id, self.auction_manager)
        
        # Add cancel button for admins
        cancel_button = CancelButton(auction_id, self.auction_manager)
        view.add_item(cancel_button)
        
        # Send initial response to the interaction
        await interaction.response.send_message(
            f"✅ Creating auction for **{item_name}**...",
            ephemeral=True
        )
        
        # Send the auction embed to the channel
        message = await interaction.channel.send(embed=embed, view=view)
        
        # Update the auction with the message ID
        self.auction_manager.set_message_id(auction_id, message.id)
        
        # Send public confirmation
        await interaction.channel.send(
            f"✅ Auction for **{item_name}** has been started by {interaction.user.mention}! It will end <t:{int(auction.end_time.timestamp())}:R>."
        )
    
    # Slash command for ending auctions early
    @app_commands.command(name="end", description="End an auction early (admin only)")
    @app_commands.describe(auction_id="ID of the auction to end")
    @app_commands.checks.has_permissions(administrator=True)
    async def auction_end(self, interaction: discord.Interaction, auction_id: int):
        """End an auction early (admin only)"""
        auction = self.auction_manager.get_auction(auction_id)
        if not auction:
            await interaction.response.send_message("❌ Auction not found.", ephemeral=True)
            return
        
        if auction.ended:
            await interaction.response.send_message("❌ This auction has already ended.", ephemeral=True)
            return
        
        # End the auction
        self.auction_manager.end_auction(auction_id)
        
        # Update the auction message
        try:
            channel = self.bot.get_channel(auction.channel_id)
            if channel:
                message = await channel.fetch_message(auction.message_id)
                if message:
                    embed = discord.Embed(
                        title=f"Auction: {auction.item_name} [ENDED EARLY]",
                        description=f"This auction was ended early by an administrator.",
                        color=discord.Color.orange()
                    )
                    
                    if auction.highest_bidder_id:
                        winner = self.bot.get_user(auction.highest_bidder_id)
                        winner_mention = winner.mention if winner else f"User ID: {auction.highest_bidder_id}"
                        
                        # Display winner according to anonymous setting
                        if auction.anonymous_bidding:
                            embed.add_field(
                                name="Winner", 
                                value="Anonymous",
                                inline=True
                            )
                            
                            # Private notification to winner
                            try:
                                if winner:
                                    await winner.send(f"🏆 Congratulations! You won the auction for **{auction.item_name}** with a bid of **{auction.highest_bid} {auction.currency}**!")
                            except:
                                # Could not DM the winner
                                pass
                                
                            # Public announcement without mentioning the winner
                            await channel.send(
                                f"🏆 **Auction Ended Early!** The auction for **{auction.item_name}** has ended with a winning bid of **{auction.highest_bid} {auction.currency}**. The winner has been notified."
                            )
                        else:
                            embed.add_field(
                                name="Winner", 
                                value=winner_mention,
                                inline=True
                            )
                            
                            # Announce the winner publicly
                            await channel.send(
                                f"🏆 **Auction Ended Early!** Congratulations to {winner_mention} for winning the **{auction.item_name}** with a bid of **{auction.highest_bid} {auction.currency}**!"
                            )
                            
                        embed.add_field(
                            name="Winning Bid", 
                            value=f"{auction.highest_bid} {auction.currency}",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="Result", 
                            value="No bids were placed.",
                            inline=False
                        )
                        
                        # Announce no winner
                        await channel.send(
                            f"⏱️ **Auction Ended Early!** The auction for **{auction.item_name}** has ended with no bids."
                        )
                    
                    await message.edit(embed=embed, view=None)
                    
                    await interaction.response.send_message(
                        f"✅ Auction #{auction_id} for **{auction.item_name}** has been ended.",
                        ephemeral=True
                    )
        except Exception as e:
            await interaction.response.send_message(
                f"⚠️ Could not update the original auction message: {e}",
                ephemeral=True
            )
    
    # Slash command for listing active auctions
    @app_commands.command(name="list", description="List all active auctions")
    async def auction_list(self, interaction: discord.Interaction):
        """List all active auctions"""
        active_auctions = self.auction_manager.get_active_auctions()
        
        if not active_auctions:
            await interaction.response.send_message("📢 There are no active auctions at the moment.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="Active Auctions",
            description="Here are all the current active auctions:",
            color=discord.Color.blue()
        )
        
        for auction_id, auction in active_auctions.items():
            # Display emblem if available and not auto-deleted
            embed_str = ""
            if auction.emblem_url and not (auction.ended and auction.auto_delete_emblem):
                embed_str = f"[📷]({auction.emblem_url}) "
                
            # Handle highest bidder display based on anonymous setting
            if auction.highest_bidder_name and auction.anonymous_bidding:
                bidder_display = "Anonymous"
            else:
                bidder_display = auction.highest_bidder_name if auction.highest_bidder_name else 'None'
                
            embed.add_field(
                name=f"{embed_str}#{auction_id}: {auction.item_name}",
                value=(
                    f"Owner: <@{auction.creator_id}>\n"
                    f"Current Bid: {auction.highest_bid} {auction.currency}\n"
                    f"Highest Bidder: {bidder_display}\n"
                    f"Ends: <t:{int(auction.end_time.timestamp())}:R>\n"
                    f"[Jump to Auction](https://discord.com/channels/{interaction.guild_id}/{auction.channel_id}/{auction.message_id})"
                ),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    # Slash command for getting auction info
    @app_commands.command(name="info", description="Get detailed information about an auction")
    @app_commands.describe(auction_id="ID of the auction to get info about")
    async def auction_info(self, interaction: discord.Interaction, auction_id: int):
        """Get detailed information about an auction"""
        auction = self.auction_manager.get_auction(auction_id)
        if not auction:
            await interaction.response.send_message("❌ Auction not found.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"Auction Info: {auction.item_name}",
            color=discord.Color.blue()
        )
        
        # Set emblem image if available and not auto-deleted
        if auction.emblem_url and not (auction.ended and auction.auto_delete_emblem):
            embed.set_thumbnail(url=auction.emblem_url)
        
        # Get owner name
        try:
            owner = self.bot.get_user(auction.creator_id)
            owner_name = owner.name if owner else f"User ID: {auction.creator_id}"
        except:
            owner_name = f"User ID: {auction.creator_id}"
        
        # Add owner field
        embed.add_field(
            name="Owner", 
            value=f"{owner_name} (<@{auction.creator_id}>)", 
            inline=True
        )
        
        # Add currency field
        embed.add_field(
            name="Currency", 
            value=auction.currency, 
            inline=True
        )
        
        # Add auction ID
        embed.add_field(name="Auction ID", value=str(auction_id), inline=True)
        
        # Add auction details
        embed.add_field(
            name="Starting Bid", 
            value=f"{auction.starting_bid} {auction.currency}", 
            inline=True
        )
        
        embed.add_field(
            name="Bid Increment", 
            value=f"{auction.bid_increment} {auction.currency}", 
            inline=True
        )
        
        # Add current status
        if auction.ended:
            status = "Ended"
            if auction.cancelled:
                status += " (Cancelled)"
        else:
            status = "Active"
        
        embed.add_field(name="Status", value=status, inline=True)
        
        # Add best offer and highest bidder info
        if auction.highest_bidder_id:
            # Check if the auction has anonymous bidding enabled
            if auction.anonymous_bidding:
                bidder_name = "Anonymous"
            else:
                highest_bidder = self.bot.get_user(auction.highest_bidder_id)
                bidder_name = highest_bidder.name if highest_bidder else auction.highest_bidder_name
                
            embed.add_field(
                name="Highest Bidder", 
                value=bidder_name, 
                inline=True
            )
            embed.add_field(
                name="Best Offer", 
                value=f"{auction.highest_bid} {auction.currency}", 
                inline=True
            )
        else:
            embed.add_field(
                name="Highest Bidder", 
                value="None", 
                inline=True
            )
            embed.add_field(
                name="Best Offer", 
                value=f"{auction.starting_bid} {auction.currency} (Starting Bid)", 
                inline=True
            )
        
        # Add time information
        created_at = int(auction.created_at.timestamp())
        embed.add_field(
            name="Created At", 
            value=f"<t:{created_at}:F> (<t:{created_at}:R>)", 
            inline=False
        )
        
        end_time = int(auction.end_time.timestamp())
        embed.add_field(
            name="Ends At", 
            value=f"<t:{end_time}:F> (<t:{end_time}:R>)", 
            inline=False
        )
        
        # Add jump link
        embed.add_field(
            name="Auction Link",
            value=f"[Jump to Auction](https://discord.com/channels/{interaction.guild_id}/{auction.channel_id}/{auction.message_id})",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    # Slash command for help
    @app_commands.command(name="help", description="Show help for auction commands")
    async def auction_help(self, interaction: discord.Interaction):
        """Show help for auction commands"""
        embed = discord.Embed(
            title="Auction System Help",
            description="Here are the available auction commands:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="/auction start",
            value=(
                "Start a new auction\n"
                "Parameters:\n"
                "- duration: Time duration (e.g., 1h, 30m, 1d, 1d12h)\n"
                "- starting_bid: Initial bid amount\n"
                "- bid_increment: Minimum bid increase\n"
                "- item_name: Name of the item being auctioned\n"
                "- currency: Optional, type of currency (default: coins)\n"
                "- emblem_url: Optional, URL to an image for the auction\n"
                "- anonymous: Optional, 'yes' or 'no' (default: 'no'). Hides bidder identities\n"
                "- auto_delete_emblem: Optional, 'yes' or 'no' (default: 'no'). Removes emblem after auction ends"
            ),
            inline=False
        )
        
        embed.add_field(
            name="/auction end <auction_id>",
            value="End an auction early (admin only)",
            inline=False
        )
        
        embed.add_field(
            name="/auction list",
            value="List all active auctions",
            inline=False
        )
        
        embed.add_field(
            name="/auction info <auction_id>",
            value="Get detailed information about an auction",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(AuctionCog(bot))
